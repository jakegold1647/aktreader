"""Offline generation and ingestion of evidence-loaded human adjudication packets."""

from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

from aktreader.batch import atomic_write_json, atomic_write_text

PACKET_VERSION = "1.0.0"
NEITHER_CHOICE = "NEITHER_OR_SOMETHING_ELSE"
CANT_TELL_CHOICE = "CANT_TELL"
_PRIORITY = {
    "IDENTITY_FORK": 0,
    "MACHINE_DEADLOCK": 1,
    "CORROBORATION_CONFLICT": 2,
    "GOLD_SINGLE_COVERAGE": 3,
}
_MANDATORY_REASONS = frozenset({"IDENTITY_FORK", "MACHINE_DEADLOCK"})
_SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]+$")


class AdjudicationError(ValueError):
    """Raised when a packet cannot be built or ingested without guessing."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise AdjudicationError(f"duplicate JSON key is forbidden: {key!r}")
        value[key] = child
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _load_object(path: Path, *, role: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                AdjudicationError(f"non-standard JSON number is forbidden: {value}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AdjudicationError(f"{role} is not readable strict JSON: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise AdjudicationError(f"{role} must contain one JSON object: {path}")
    return payload


def _validate(schema_path: Path, payload: Mapping[str, Any], *, role: str) -> None:
    schema = _load_object(schema_path, role=f"{role} schema")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise AdjudicationError(f"{role}.{location}: {error.message}")


def _require_unique_ids(spec: Mapping[str, Any]) -> None:
    def require(items: Sequence[Mapping[str, Any]], key: str, role: str) -> None:
        values = [str(item[key]) for item in items]
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise AdjudicationError(f"{role} contains duplicate IDs: {duplicates}")

    require(spec["questions"], "question_id", "adjudication wave.questions")
    require(spec["exemplar_catalog"], "exemplar_id", "adjudication wave.exemplar_catalog")
    for question in spec["questions"]:
        require(
            question["candidates"],
            "candidate_id",
            f"{question['question_id']}.candidates",
        )


def _resolve_local_path(raw: Any, *, base: Path, role: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise AdjudicationError(f"{role}.path must be a nonblank local path")
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise AdjudicationError(f"{role}.path must not be a URL or UNC path")
    path = Path(raw)
    resolved = (path if path.is_absolute() else base / path).resolve(strict=True)
    if not resolved.is_file():
        raise AdjudicationError(f"{role}.path is not a file: {resolved}")
    return resolved


def _verify_artifact(
    raw: Mapping[str, Any],
    *,
    base: Path,
    role: str,
) -> Path:
    path = _resolve_local_path(raw.get("path"), base=base, role=role)
    expected = raw.get("sha256")
    actual = _sha256_file(path)
    if expected != actual:
        raise AdjudicationError(f"{role}.sha256 mismatch: expected {expected!r}, got {actual}")
    return path


def _bbox_tuple(raw: Mapping[str, Any], *, role: str) -> tuple[int, int, int, int]:
    try:
        x = int(raw["x"])
        y = int(raw["y"])
        width = int(raw["width"])
        height = int(raw["height"])
    except (KeyError, TypeError, ValueError) as error:
        raise AdjudicationError(f"{role} is not a valid source-pixel bbox") from error
    return (x, y, x + width, y + height)


def _crop_png(
    artifact: Mapping[str, Any],
    *,
    base: Path,
    role: str,
    magnification: int,
    glyph: bool = False,
    text: str | None = None,
) -> tuple[str, str]:
    path = _verify_artifact(artifact, base=base, role=role)
    bbox = artifact.get("glyph_bbox") if glyph else artifact.get("bbox")
    approximation = ""
    if glyph and not isinstance(bbox, Mapping):
        word_bbox = artifact.get("bbox")
        index = artifact.get("character_index")
        if not isinstance(word_bbox, Mapping) or not isinstance(index, int) or not text:
            raise AdjudicationError(f"{role}: glyph_bbox or text plus character_index is required")
        if index >= len(text):
            raise AdjudicationError(f"{role}.character_index exceeds exemplar text")
        x = int(word_bbox["x"])
        width = int(word_bbox["width"])
        left = x + round(width * index / len(text))
        right = x + round(width * (index + 1) / len(text))
        bbox = {
            "x": left,
            "y": int(word_bbox["y"]),
            "width": max(1, right - left),
            "height": int(word_bbox["height"]),
        }
        approximation = "proportional character segmentation; full word shown beside it"
    if not isinstance(bbox, Mapping):
        raise AdjudicationError(f"{role}: missing bbox")
    with Image.open(path) as source:
        source.load()
        bounds = _bbox_tuple(bbox, role=f"{role}.bbox")
        if bounds[0] < 0 or bounds[1] < 0 or bounds[2] > source.width or bounds[3] > source.height:
            raise AdjudicationError(
                f"{role}.bbox {bounds} exceeds image dimensions {source.width}x{source.height}"
            )
        crop = source.crop(bounds)
        crop = crop.resize(
            (crop.width * magnification, crop.height * magnification),
            Image.Resampling.NEAREST,
        )
        output = io.BytesIO()
        crop.save(output, format="PNG", optimize=False)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}", approximation


def select_questions(
    questions: Sequence[Mapping[str, Any]],
    *,
    max_questions: int = 10,
) -> list[Mapping[str, Any]]:
    """Rank decision-bearing questions; mandatory forks survive a nominal cap."""
    if isinstance(max_questions, bool) or not isinstance(max_questions, int) or max_questions < 1:
        raise AdjudicationError("max_questions must be a positive integer")
    eligible = [question for question in questions if question.get("selection_reason") in _PRIORITY]
    ranked = sorted(
        eligible,
        key=lambda question: (
            _PRIORITY[str(question["selection_reason"])],
            str(question["question_id"]).casefold(),
        ),
    )
    mandatory = [
        question for question in ranked if question["selection_reason"] in _MANDATORY_REASONS
    ]
    optional = [
        question for question in ranked if question["selection_reason"] not in _MANDATORY_REASONS
    ]
    if len(mandatory) >= max_questions:
        return mandatory
    return mandatory + optional[: max_questions - len(mandatory)]


def mine_lineup(
    question: Mapping[str, Any],
    exemplar_catalog: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    """Choose 3–6 uncontested same-clerk-year exemplars for every candidate glyph."""
    clerk_year_id = question["clerk_year_id"]
    result: dict[str, list[Mapping[str, Any]]] = {}
    for candidate in question["candidates"]:
        matches = sorted(
            (
                exemplar
                for exemplar in exemplar_catalog
                if exemplar.get("clerk_year_id") == clerk_year_id
                and exemplar.get("glyph") == candidate["glyph"]
                and exemplar.get("confidence") == "UNCONTESTED"
            ),
            key=lambda exemplar: str(exemplar["exemplar_id"]).casefold(),
        )
        if len(matches) < 3:
            raise AdjudicationError(
                f"{question['question_id']}: candidate {candidate['candidate_id']} glyph "
                f"{candidate['glyph']!r} has {len(matches)} same-clerk uncontested exemplars; "
                "3 are required"
            )
        result[str(candidate["candidate_id"])] = matches[:6]
    return result


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _render_question(
    question: Mapping[str, Any],
    lineup: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    base: Path,
) -> tuple[str, dict[str, Any]]:
    question_id = str(question["question_id"])
    magnification = int(question.get("magnification", 6))
    disputed_uri, _ = _crop_png(
        question["artifact"],
        base=base,
        role=f"{question_id}.artifact",
        magnification=magnification,
    )
    disputed_glyph_uri, _ = _crop_png(
        question["artifact"],
        base=base,
        role=f"{question_id}.artifact.glyph",
        magnification=magnification,
        glyph=True,
    )
    candidate_by_id = {
        str(candidate["candidate_id"]): candidate for candidate in question["candidates"]
    }
    lineup_html: list[str] = []
    lineup_manifest: dict[str, list[str]] = {}
    for candidate_id, exemplars in lineup.items():
        candidate = candidate_by_id[candidate_id]
        cards: list[str] = []
        exemplar_ids: list[str] = []
        for exemplar in exemplars:
            exemplar_id = str(exemplar["exemplar_id"])
            exemplar_ids.append(exemplar_id)
            glyph_uri, approximation = _crop_png(
                exemplar["artifact"],
                base=base,
                role=f"{question_id}.exemplar.{exemplar_id}",
                magnification=magnification,
                glyph=True,
                text=str(exemplar["text"]),
            )
            word_uri, _ = _crop_png(
                exemplar["artifact"],
                base=base,
                role=f"{question_id}.exemplar.{exemplar_id}",
                magnification=magnification,
            )
            approximation_html = (
                f'<small class="warning">{_esc(approximation)}</small>'
                if approximation
                else "<small>explicit glyph box</small>"
            )
            cards.append(
                '<figure class="exemplar">'
                f'<img src="{glyph_uri}" alt="glyph {_esc(candidate["glyph"])}">'
                f'<img class="word" src="{word_uri}" alt="{_esc(exemplar["label"])}">'
                f"<figcaption>{_esc(exemplar['label'])}: "
                f"<code>{_esc(exemplar['text'])}</code>{approximation_html}</figcaption>"
                "</figure>"
            )
        lineup_manifest[candidate_id] = exemplar_ids
        lineup_html.append(
            '<section class="candidate-column">'
            f"<h4>{_esc(candidate['label'])} — glyph "
            f'<span class="glyph">{_esc(candidate["glyph"])}</span></h4>'
            f"{''.join(cards)}</section>"
        )

    anchor_html: list[str] = []
    for index, anchor in enumerate(question["bilingual_anchors"]):
        uri, _ = _crop_png(
            anchor["artifact"],
            base=base,
            role=f"{question_id}.anchor.{index}",
            magnification=magnification,
        )
        anchor_html.append(
            '<figure class="anchor">'
            f'<img src="{uri}" alt="{_esc(anchor["label"])}">'
            f"<figcaption><strong>{_esc(anchor['label'])}</strong>: "
            f"{_esc(anchor['plain_text'])}</figcaption></figure>"
        )
    check_html = "".join(
        f'<li class="{_esc(check["result"].lower())}">'
        f"<strong>{_esc(check['label'])} — {_esc(check['result'])}:</strong> "
        f"{_esc(check['interpretation'])}</li>"
        for check in question["structural_checks"]
    )
    choice_html = "".join(
        '<label class="choice">'
        f'<input type="radio" name="{_esc(question_id)}" '
        f'value="{_esc(candidate["candidate_id"])}">'
        f"<span><strong>{_esc(candidate['label'])}</strong><br>"
        f"Consequence: {_esc(candidate['consequence'])}</span></label>"
        for candidate in question["candidates"]
    )
    choice_html += (
        '<label class="choice escape"><input type="radio" '
        f'name="{_esc(question_id)}" value="{NEITHER_CHOICE}">'
        "<span><strong>Neither / something else</strong><br>"
        f"Consequence: {_esc(question['neither_consequence'])}</span></label>"
        '<label class="choice escape"><input type="radio" '
        f'name="{_esc(question_id)}" value="{CANT_TELL_CHOICE}">'
        "<span><strong>Can't tell</strong><br>"
        f"Consequence: {_esc(question['cant_tell_consequence'])}</span></label>"
    )
    section = (
        f'<article class="question" data-question-id="{_esc(question_id)}">'
        f"<header><span>Question {_esc(question_id)}</span>"
        f"<span>{_esc(question['selection_reason'])}</span></header>"
        f"<h2>{_esc(question['claim'])}</h2>"
        '<p class="limit"><strong>Honest limit:</strong> compare the proposed shapes. '
        "This is not independent transcription; both proposals may be wrong.</p>"
        f'<img class="disputed" src="{disputed_uri}" alt="magnified disputed region">'
        f'<img class="disputed-glyph" src="{disputed_glyph_uri}" '
        'alt="magnified disputed glyph">'
        f'<p class="magnification">Original pixels shown at {magnification}× nearest-neighbor.</p>'
        "<h3>Same-hand letterform lineup</h3>"
        f'<div class="lineup">{"".join(lineup_html)}</div>'
        f'<div class="anchors">{"".join(anchor_html)}</div>'
        f'<ul class="checks">{check_html}</ul>'
        f"<h3>{_esc(question['question'])}</h3>"
        f'<div class="choices">{choice_html}</div>'
        '<label>Verbatim answer<textarea class="verbatim" rows="2"></textarea></label>'
        '<label>Interpretation<textarea class="interpretation" rows="2"></textarea></label>'
        '<fieldset class="methods"><legend>Evidence used</legend>'
        '<label><input type="checkbox" value="LETTERFORM_LINEUP"> Letterform lineup</label>'
        '<label><input type="checkbox" value="BILINGUAL_ANCHOR"> Bilingual anchor</label>'
        '<label><input type="checkbox" value="INDEX_CROSS_CHECK"> Index cross-check</label>'
        '<label><input type="checkbox" value="DIRECT_SCRIPT_READING"> Direct script reading</label>'
        '<label><input type="checkbox" value="STRUCTURAL_CROSS_CHECK"> Structural check</label>'
        "</fieldset></article>"
    )
    return section, {
        "question_id": question_id,
        "record_id": question["record_id"],
        "record_sha256": question["record_sha256"],
        "field_path": question["field_path"],
        "clerk_year_id": question["clerk_year_id"],
        "selection_reason": question["selection_reason"],
        "artifact_sha256": question["artifact"]["sha256"],
        "artifact_bbox": question["artifact"]["bbox"],
        "candidate_ids": list(candidate_by_id),
        "candidates": list(question["candidates"]),
        "lineup_exemplar_ids": lineup_manifest,
        "neither_consequence": question["neither_consequence"],
        "cant_tell_consequence": question["cant_tell_consequence"],
    }


def _render_html(
    *,
    packet_id: str,
    wave_id: str,
    title: str,
    sections: Sequence[str],
    spec_sha256: str,
    questions_sha256: str,
) -> str:
    bootstrap = json.dumps(
        {
            "$schema": "../../schemas/adjudication-answers-1.0.0.schema.json",
            "schema_version": PACKET_VERSION,
            "packet_id": packet_id,
            "wave_id": wave_id,
            "spec_sha256": spec_sha256,
            "questions_sha256": questions_sha256,
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<style>
:root {{ color-scheme: light dark; --bg:#f3efe4; --card:#fffdf7; --ink:#211d18;
--muted:#6a6259; --accent:#8b3d2f; --line:#c9bdad; }}
@media (prefers-color-scheme:dark) {{ :root {{ --bg:#171614; --card:#23211e; --ink:#f1ece2;
--muted:#b8afa4; --accent:#ef9b82; --line:#554e46; }} }}
* {{ box-sizing:border-box }} body {{ margin:0;background:var(--bg);color:var(--ink);
font:17px/1.5 Georgia,serif }} main {{ max-width:1180px;margin:auto;padding:2rem }}
.intro,.question {{ background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:1.4rem;margin:0 0 1.5rem;box-shadow:0 8px 28px #0002 }}
header {{ display:flex;justify-content:space-between;color:var(--muted);font:700 13px system-ui;
letter-spacing:.07em }} h1,h2,h3,h4 {{ line-height:1.15 }} .limit {{ border-left:5px solid
var(--accent);padding:.7rem 1rem;background:#8b3d2f12 }} .disputed {{ display:block;max-width:100%;
image-rendering:pixelated;border:2px solid var(--ink);margin:1rem auto }} .magnification,small {{
color:var(--muted) }} .lineup {{ display:grid;
grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
gap:1rem }} .candidate-column {{ border:1px solid var(--line);border-radius:10px;padding:1rem }}
.glyph {{ font-size:1.5em }} .exemplar {{ display:grid;grid-template-columns:72px 1fr;gap:.6rem;
align-items:center;margin:1rem 0 }} .exemplar img {{ max-width:72px;image-rendering:pixelated }}
.exemplar img.word {{ max-width:100% }} figcaption {{ grid-column:1/-1 }} .warning {{ display:block;
color:#c66 }} .anchors {{ display:flex;gap:1rem;flex-wrap:wrap }} .anchor img {{ max-width:380px;
image-rendering:pixelated }} .choices {{ display:grid;gap:.6rem }}
.choice {{ display:flex;gap:.7rem;
padding:.8rem;border:1px solid var(--line);border-radius:8px }}
.escape {{ border-color:var(--accent) }}
textarea,input[type=text],select {{ width:100%;margin:.3rem 0 1rem;padding:.7rem;font:inherit }}
.methods {{ display:grid;gap:.4rem }}
button {{ padding:.8rem 1.2rem;font-weight:700;cursor:pointer }}
</style></head><body><main>
<section class="intro"><h1>{_esc(title)}</h1>
<p>Choose only what your eyes and the supplied checks support. “Neither / something else” and
“Can’t tell” are successful outcomes when the evidence does not decide.</p>
<label>Verifier ID<input id="verifier" type="text"></label>
<label>Script expertise<select id="expertise"><option>NON_READER</option><option>READER</option>
<option>VERIFIED_EXPERT</option></select></label>
<label>Correction reuse consent<select id="consent"><option>NOT_RECORDED</option>
<option>DECLINED</option><option>GRANTED</option></select></label></section>
{"".join(sections)}
<button id="download">Download answers JSON</button>
<script>
const bootstrap={bootstrap};
document.getElementById("download").addEventListener("click",()=>{{
 const answers=[...document.querySelectorAll(".question")].map(q=>({{
  question_id:q.dataset.questionId,
  choice_id:q.querySelector("input[type=radio]:checked")?.value||"",
  verbatim_answer:q.querySelector(".verbatim").value.trim(),
  interpretation:q.querySelector(".interpretation").value.trim(),
  methods:[...q.querySelectorAll(".methods input:checked")].map(x=>x.value)
 }}));
 const status=document.getElementById("consent").value;
 const payload={{...bootstrap,verifier:{{
  verifier_id:document.getElementById("verifier").value.trim(),
  script_expertise:document.getElementById("expertise").value,
  correction_consent:{{status,training_eligible:status==="GRANTED"}}
 }},answered_at:new Date().toISOString(),answers}};
 const blob=new Blob([JSON.stringify(payload,null,2)+"\\n"],{{type:"application/json"}});
 const a=document.createElement("a"); a.href=URL.createObjectURL(blob);
 a.download=bootstrap.packet_id+".answers.json"; a.click(); URL.revokeObjectURL(a.href);
}});
</script></main></body></html>
"""


def generate_packet(
    *,
    project_root: Path,
    spec_path: Path,
    output_dir: Path,
    wave_id: str,
    max_questions: int = 10,
    replace_existing: bool = False,
) -> dict[str, Any]:
    """Validate one wave specification and render a self-contained offline packet."""
    root = project_root.resolve()
    spec_path = spec_path.resolve(strict=True)
    output_dir = output_dir.resolve()
    spec = _load_object(spec_path, role="adjudication wave")
    _validate(
        root / "schemas" / "adjudication-wave-1.0.0.schema.json",
        spec,
        role="adjudication wave",
    )
    _require_unique_ids(spec)
    if not _SAFE_ID.fullmatch(wave_id) or spec["wave_id"] != wave_id:
        raise AdjudicationError(
            f"--wave {wave_id!r} does not match specification wave_id {spec['wave_id']!r}"
        )
    selected = select_questions(spec["questions"], max_questions=max_questions)
    if not selected:
        raise AdjudicationError("selection policy produced no adjudication questions")
    packet_id = f"adjudication-wave-{wave_id}"
    packet_path = output_dir / "packet.html"
    protected = (packet_path, output_dir / "manifest.json", output_dir / "questions.json")
    if any(path.exists() for path in protected) and not replace_existing:
        raise AdjudicationError(
            f"packet output already exists at {output_dir}; pass --replace-existing"
        )
    if replace_existing and (output_dir / "results").exists():
        raise AdjudicationError(
            "packet has ingested results and cannot be replaced; generate a new output directory"
        )

    sections: list[str] = []
    question_manifest: list[dict[str, Any]] = []
    for question in selected:
        lineup = mine_lineup(question, spec["exemplar_catalog"])
        section, manifest_item = _render_question(
            question,
            lineup,
            base=spec_path.parent,
        )
        sections.append(section)
        question_manifest.append(manifest_item)

    questions_payload = {
        "schema_version": PACKET_VERSION,
        "packet_id": packet_id,
        "wave_id": wave_id,
        "questions": question_manifest,
    }
    spec_sha256 = _sha256_file(spec_path)
    questions_sha256 = _sha256_bytes(_canonical_json_bytes(questions_payload))
    packet_html = _render_html(
        packet_id=packet_id,
        wave_id=wave_id,
        title=str(spec["title"]),
        sections=sections,
        spec_sha256=spec_sha256,
        questions_sha256=questions_sha256,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_dir / "questions.json", questions_payload)
    atomic_write_text(packet_path, packet_html)
    answers_template = {
        "$schema": "../../../schemas/adjudication-answers-1.0.0.schema.json",
        "schema_version": PACKET_VERSION,
        "packet_id": packet_id,
        "wave_id": wave_id,
        "spec_sha256": spec_sha256,
        "questions_sha256": questions_sha256,
        "verifier": {
            "verifier_id": "FILL_ME",
            "script_expertise": "NON_READER",
            "correction_consent": {
                "status": "NOT_RECORDED",
                "training_eligible": False,
            },
        },
        "answered_at": "FILL_ME_ISO_8601",
        "answers": [
            {
                "question_id": item["question_id"],
                "choice_id": "FILL_ME",
                "verbatim_answer": "FILL_ME",
                "interpretation": "FILL_ME",
                "methods": ["LETTERFORM_LINEUP"],
            }
            for item in question_manifest
        ],
    }
    atomic_write_json(output_dir / "answers.template.json", answers_template)
    manifest = {
        "schema_version": PACKET_VERSION,
        "packet_id": packet_id,
        "wave_id": wave_id,
        "spec_path": str(spec_path),
        "spec_sha256": spec_sha256,
        "questions_sha256": questions_sha256,
        "packet_sha256": _sha256_file(packet_path),
        "question_count": len(question_manifest),
        "nominal_question_cap": max_questions,
        "mandatory_questions_exceeded_cap": len(question_manifest) > max_questions,
        "network_required": False,
        "images_embedded": True,
        "answer_ingest_mutates_labels": False,
    }
    atomic_write_json(output_dir / "manifest.json", manifest)
    return {
        "status": "GENERATED",
        "packet": str(packet_path),
        "manifest": str(output_dir / "manifest.json"),
        "answers_template": str(output_dir / "answers.template.json"),
        "question_count": len(question_manifest),
        "packet_sha256": manifest["packet_sha256"],
        "network_required": False,
    }


def _consequence(question: Mapping[str, Any], choice_id: str) -> str:
    if choice_id == NEITHER_CHOICE:
        return str(question["neither_consequence"])
    if choice_id == CANT_TELL_CHOICE:
        return str(question["cant_tell_consequence"])
    candidates = {str(candidate["candidate_id"]): candidate for candidate in question["candidates"]}
    return str(candidates[choice_id]["consequence"])


def ingest_answers(
    *,
    project_root: Path,
    packet_dir: Path,
    answers_path: Path,
) -> dict[str, Any]:
    """Validate answers and emit immutable downstream events without rewriting labels."""
    root = project_root.resolve()
    packet_dir = packet_dir.resolve(strict=True)
    answers_path = answers_path.resolve(strict=True)
    manifest = _load_object(packet_dir / "manifest.json", role="packet manifest")
    questions_payload = _load_object(packet_dir / "questions.json", role="packet questions")
    answers = _load_object(answers_path, role="adjudication answers")
    required_manifest = {
        "packet_id",
        "wave_id",
        "spec_sha256",
        "questions_sha256",
        "packet_sha256",
    }
    missing_manifest = sorted(required_manifest - set(manifest))
    if missing_manifest:
        raise AdjudicationError(f"packet manifest is missing keys: {missing_manifest}")
    packet_path = packet_dir / "packet.html"
    if not packet_path.is_file() or _sha256_file(packet_path) != manifest["packet_sha256"]:
        raise AdjudicationError("packet HTML digest no longer matches its manifest")
    if not isinstance(questions_payload.get("questions"), list):
        raise AdjudicationError("packet questions must contain a questions list")

    _validate(
        root / "schemas" / "adjudication-answers-1.0.0.schema.json",
        answers,
        role="adjudication answers",
    )
    for key in ("packet_id", "wave_id", "spec_sha256", "questions_sha256"):
        expected = manifest[key]
        if answers.get(key) != expected:
            raise AdjudicationError(f"adjudication answers.{key} does not match packet")
    actual_questions_sha256 = _sha256_bytes(_canonical_json_bytes(questions_payload))
    if actual_questions_sha256 != manifest["questions_sha256"]:
        raise AdjudicationError("packet questions digest no longer matches its manifest")

    question_by_id = {
        str(question["question_id"]): question for question in questions_payload["questions"]
    }
    answer_by_id: dict[str, Mapping[str, Any]] = {}
    for answer in answers["answers"]:
        question_id = str(answer["question_id"])
        if question_id in answer_by_id:
            raise AdjudicationError(f"duplicate answer for {question_id}")
        answer_by_id[question_id] = answer
    if set(answer_by_id) != set(question_by_id):
        missing = sorted(set(question_by_id) - set(answer_by_id))
        unexpected = sorted(set(answer_by_id) - set(question_by_id))
        raise AdjudicationError(
            f"answer question IDs differ from packet; missing={missing}, unexpected={unexpected}"
        )

    consent = answers["verifier"]["correction_consent"]
    definitive_events: list[dict[str, Any]] = []
    expert_review: list[dict[str, Any]] = []
    tier_actions: list[dict[str, Any]] = []
    attestation_events: list[dict[str, Any]] = []
    result_answers: list[dict[str, Any]] = []
    for question_id, question in question_by_id.items():
        answer = answer_by_id[question_id]
        choice_id = str(answer["choice_id"])
        candidate_ids = set(question["candidate_ids"])
        allowed = candidate_ids | {NEITHER_CHOICE, CANT_TELL_CHOICE}
        if choice_id not in allowed:
            raise AdjudicationError(
                f"{question_id}: choice_id {choice_id!r} is not a packet choice"
            )
        consequence = _consequence(question, choice_id)
        result_answers.append(
            {
                **dict(answer),
                "declared_consequence": consequence,
                "consequence_execution": "EVENT_EMITTED_NO_LABEL_MUTATION",
            }
        )
        if choice_id in candidate_ids:
            selected = next(
                item for item in question["candidates"] if item["candidate_id"] == choice_id
            )
            event = {
                "question_id": question_id,
                "packet_id": manifest["packet_id"],
                "packet_sha256": manifest["packet_sha256"],
                "artifact_sha256": question["artifact_sha256"],
                "artifact_bbox": question["artifact_bbox"],
                "record_id": question["record_id"],
                "record_sha256": question["record_sha256"],
                "field_path": question["field_path"],
                "selected_candidate_id": choice_id,
                "selected_value": selected["value"],
                "verbatim_answer": answer["verbatim_answer"],
                "interpretation": answer["interpretation"],
                "answered_at": answers["answered_at"],
                "verifier": answers["verifier"],
                "training_eligible": (
                    consent["status"] == "GRANTED" and consent["training_eligible"] is True
                ),
            }
            definitive_events.append(event)
            tier_actions.append(
                {
                    "action": "APPLY_DECLARED_CONSEQUENCE",
                    "record_id": question["record_id"],
                    "field_path": question["field_path"],
                    "declared_consequence": consequence,
                    "automatic_record_mutation": False,
                }
            )
            attestation_events.append(
                {
                    "record_id": question["record_id"],
                    "record_sha256": question["record_sha256"],
                    "field_path": question["field_path"],
                    "evidence_class": "VERIFIED_FROM_IMAGE",
                    "image_reference": {
                        "artifact_sha256": question["artifact_sha256"],
                        "region": question["artifact_bbox"],
                    },
                    "attestation": {
                        "attestor_id": answers["verifier"]["verifier_id"],
                        "method": answer["methods"][0],
                        "attested_at": answers["answered_at"],
                        "verbatim_answer": answer["verbatim_answer"],
                        "adjudication_packet_sha256": manifest["packet_sha256"],
                    },
                    "benchmark_eligible": True,
                }
            )
        else:
            expert_review.append(
                {
                    "question_id": question_id,
                    "record_id": question["record_id"],
                    "field_path": question["field_path"],
                    "outcome": choice_id,
                    "verbatim_answer": answer["verbatim_answer"],
                    "interpretation": answer["interpretation"],
                    "next_step": consequence,
                }
            )
            tier_actions.append(
                {
                    "action": "PRESERVE_UNCLEAR_AND_ROUTE_EXPERT",
                    "record_id": question["record_id"],
                    "field_path": question["field_path"],
                    "declared_consequence": consequence,
                    "automatic_record_mutation": False,
                }
            )

    answers_sha256 = _sha256_file(answers_path)
    result_id = answers_sha256[:16]
    result_dir = packet_dir / "results" / result_id
    if result_dir.exists():
        raise AdjudicationError(f"answer result already ingested: {result_dir}")
    results_root = result_dir.parent
    results_root.mkdir(parents=True, exist_ok=True)
    stage_dir: Path | None = Path(tempfile.mkdtemp(prefix=f".{result_id}.", dir=results_root))
    try:
        result = {
            "schema_version": PACKET_VERSION,
            "packet_id": manifest["packet_id"],
            "packet_sha256": manifest["packet_sha256"],
            "answers_path": str(answers_path),
            "answers_sha256": answers_sha256,
            "verifier": answers["verifier"],
            "answered_at": answers["answered_at"],
            "answers": result_answers,
            "label_mutations_performed": False,
        }
        atomic_write_json(stage_dir / "adjudication-results.json", result)
        atomic_write_json(
            stage_dir / "tier-actions.json",
            {"schema_version": PACKET_VERSION, "actions": tier_actions},
        )
        atomic_write_json(
            stage_dir / "gold-attestation-events.json",
            {"schema_version": PACKET_VERSION, "events": attestation_events},
        )
        atomic_write_json(
            stage_dir / "expert-review.json",
            {"schema_version": PACKET_VERSION, "items": expert_review},
        )
        correction_text = "".join(
            json.dumps(event, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
            for event in definitive_events
        )
        atomic_write_text(stage_dir / "correction-flywheel.jsonl", correction_text)
        os.replace(stage_dir, result_dir)
        stage_dir = None
    finally:
        if stage_dir is not None:
            shutil.rmtree(stage_dir, ignore_errors=True)
    return {
        "status": "INGESTED",
        "result_dir": str(result_dir),
        "definitive_answer_count": len(definitive_events),
        "expert_review_count": len(expert_review),
        "gold_attestation_event_count": len(attestation_events),
        "training_eligible_correction_count": sum(
            event["training_eligible"] for event in definitive_events
        ),
        "label_mutations_performed": False,
    }
