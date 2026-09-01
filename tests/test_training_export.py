import json
from pathlib import Path

import pytest

from aktreader.training import (
    TrainingExportError,
    build_training_export,
    build_training_readiness,
    sha256_path,
)

ROOT = Path(__file__).resolve().parents[1]
SILVER = ROOT / "labels" / "silver" / "manifest.json"
CURRENT_HOLDOUT = ROOT / "gold" / "clerk_year_holdout.json"
READER_B = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _grounded_label(
    path: Path,
    *,
    reader_id: str,
    reader_family: str,
    record_id: str = "serock-1890-death-1",
) -> None:
    payload = json.loads(
        READER_B.read_text(encoding="utf-8").replace(
            "serock-1890-death-1", record_id
        )
    )
    payload["label_id"] = f"synthetic.{reader_id}"
    payload["reader"]["reader_id"] = reader_id
    payload["reader"]["reader_family"] = reader_family
    payload["target"]["language"] = "pl"
    payload["transcription"]["original_script"] = "Fruma"
    payload["observations"] = {
        "principal.name": {
            "value": "Fruma",
            "original_script": "Fruma",
            "confidence": "PROBABLE",
            "observation_state": "PRESENT",
            "alternatives": [],
            "source_span_ids": ["principal"],
            "notes": [],
        }
    }
    _write_json(path, payload)


def _grounded_export_fixture(
    tmp_path: Path,
    *,
    record_ids: tuple[str, ...] = ("serock-1890-death-1",),
) -> tuple[Path, Path]:
    records = []
    for act_no, record_id in enumerate(record_ids, start=1):
        left = tmp_path / "labels" / f"{record_id}-left.json"
        right = tmp_path / "labels" / f"{record_id}-right.json"
        _grounded_label(
            left,
            reader_id="human-left",
            reader_family="human",
            record_id=record_id,
        )
        _grounded_label(
            right,
            reader_id="human-right",
            reader_family="human-independent",
            record_id=record_id,
        )

        record_path = tmp_path / "records" / f"{record_id}.json"
        record = {
            "record_id": record_id,
            "clerk_year": {"id": "73-826-0|serock|1890|clerk-unknown"},
            "artifact": {"path": f"image-{act_no}.jpg", "sha256": "0" * 64},
            "target": {"kind": "act", "act_no": act_no},
            "observations": {"principal.name": {"value": "Fruma"}},
            "authority_warning": "extraction is not authority — verify against the scan",
        }
        _write_json(record_path, record)
        records.append(
            {
                "record_id": record_id,
                "clerk_year_id": "73-826-0|serock|1890|clerk-unknown",
                "training_eligible": True,
                "training_materialized": True,
                "resolved_fields": {
                    "storage": "MATERIALIZED_JSON",
                    "path": f"records/{record_id}.json",
                    "sha256": sha256_path(record_path),
                },
                "provenance": {
                    "source_labels": [
                        {
                            "path": f"labels/{record_id}-left.json",
                            "sha256": sha256_path(left),
                        },
                        {
                            "path": f"labels/{record_id}-right.json",
                            "sha256": sha256_path(right),
                        },
                    ]
                },
            }
        )

    manifest_path = tmp_path / "manifest.json"
    _write_json(manifest_path, {"records": records})

    holdout_path = tmp_path / "holdout.json"
    _write_json(
        holdout_path,
        {
            "training_overlap_allowed": False,
            "holdout_clerk_year_ids": ["84|pultusk|1885|clerk-unknown"],
        },
    )
    return manifest_path, holdout_path


def test_current_gold_holdout_rejects_all_serock_1890_silver() -> None:
    with pytest.raises(TrainingExportError, match="record is not training eligible"):
        build_training_export(
            workspace_root=ROOT,
            silver_manifest_path=SILVER,
            evaluation_holdout_path=CURRENT_HOLDOUT,
        )


def test_historical_silver_fails_grounding_even_with_non_overlapping_holdout(
    tmp_path: Path,
) -> None:
    holdout = tmp_path / "holdout.json"
    _write_json(
        holdout,
        {
            "training_overlap_allowed": False,
            "holdout_clerk_year_ids": ["84|pultusk|1885|clerk-unknown"],
        },
    )

    manifest = json.loads(SILVER.read_text(encoding="utf-8"))
    for record in manifest["records"]:
        record["training_eligible"] = True
        record["training_materialized"] = True
    manifest_path = tmp_path / "legacy-eligible-manifest.json"
    _write_json(manifest_path, manifest)

    with pytest.raises(TrainingExportError, match="source label is not grounded"):
        build_training_export(
            workspace_root=ROOT,
            silver_manifest_path=manifest_path,
            evaluation_holdout_path=holdout,
        )


def test_grounded_non_overlapping_export_is_content_addressed(tmp_path: Path) -> None:
    manifest_path, holdout_path = _grounded_export_fixture(tmp_path)

    examples, manifest = build_training_export(
        workspace_root=tmp_path,
        silver_manifest_path=manifest_path,
        evaluation_holdout_path=holdout_path,
    )

    assert [example["record_id"] for example in examples] == ["serock-1890-death-1"]
    assert manifest["example_count"] == 1
    assert manifest["split_validation"] == "PASS_NO_CLERK_YEAR_OVERLAP"
    assert manifest["grounding_validation"] == "PASS_ALL_SOURCE_LABELS_GROUNDED"
    assert len(manifest["materialized_records"]) == 1


def test_training_export_ignores_manifest_record_order(tmp_path: Path) -> None:
    manifest_path, holdout_path = _grounded_export_fixture(
        tmp_path,
        record_ids=("serock-1890-death-2", "serock-1890-death-1"),
    )

    first_examples, first_manifest = build_training_export(
        workspace_root=tmp_path,
        silver_manifest_path=manifest_path,
        evaluation_holdout_path=holdout_path,
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["records"].reverse()
    _write_json(manifest_path, payload)
    second_examples, second_manifest = build_training_export(
        workspace_root=tmp_path,
        silver_manifest_path=manifest_path,
        evaluation_holdout_path=holdout_path,
    )

    assert [example["record_id"] for example in first_examples] == [
        "serock-1890-death-1",
        "serock-1890-death-2",
    ]
    assert second_examples == first_examples
    assert second_manifest["materialized_records"] == first_manifest[
        "materialized_records"
    ]


def test_holdout_must_explicitly_forbid_overlap(tmp_path: Path) -> None:
    holdout = tmp_path / "holdout.json"
    _write_json(holdout, {"holdout_clerk_year_ids": []})
    manifest = json.loads(SILVER.read_text(encoding="utf-8"))
    for record in manifest["records"]:
        record["training_eligible"] = True
        record["training_materialized"] = True
    manifest_path = tmp_path / "eligible-manifest.json"
    _write_json(manifest_path, manifest)

    with pytest.raises(TrainingExportError, match="explicitly"):
        build_training_export(
            workspace_root=ROOT,
            silver_manifest_path=manifest_path,
            evaluation_holdout_path=holdout,
        )


def test_current_training_plan_reports_measured_blockers() -> None:
    report = build_training_readiness(
        workspace_root=ROOT,
        plan_path=ROOT / "training" / "plan-0001.json",
    )

    assert report["status"] == "BLOCKED"
    assert report["paid_training_authorized"] is True
    assert report["paid_training_launch_allowed"] is False
    assert report["metrics"]["silver_record_count"] == 5
    assert report["metrics"]["grounded_training_record_count"] == 0
    assert report["metrics"]["image_attested_holdout_record_count"] == 0
    assert report["metrics"]["evaluation_overlap_clerk_year_ids"] == [
        "73-826-0|serock|1890|clerk-unknown"
    ]
    statuses = {gate["code"]: gate["status"] for gate in report["gates"]}
    assert statuses == {
        "GROUNDED_TRAINING_MINIMUM": "BLOCKED",
        "IMAGE_ATTESTED_HOLDOUT_MINIMUM": "BLOCKED",
        "CLERK_YEAR_ISOLATION": "BLOCKED",
        "TRAINER_RECIPE_PINNED": "BLOCKED",
        "CALIBRATION_SET_MINIMUM": "BLOCKED",
        "MODEL_BAKEOFF_REVISIONS_PINNED": "PASS",
    }
