"""Materialize coordinator-resolved wave 001-002 silver payloads."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "labels" / "silver" / "records"
AUTHORITY_WARNING = "extraction is not authority â€” verify against the scan"
WAVES = {
    1: (
        "labels/consensus/serock-1890-deaths-1-2_wave001_CONSENSUS.md",
        "labels/consensus/readerC_arbitration_wave001.md",
    ),
    2: (
        "labels/consensus/serock-1890-deaths-3-6_wave002_CONSENSUS.md",
        "labels/consensus/readerC_arbitration_wave002.md",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(relative: str) -> dict[str, str]:
    path = ROOT / relative
    return {"path": relative, "sha256": _sha256(path)}


def _resolved(
    base: dict[str, Any],
    *,
    value: Any,
    original_script: str | None,
    notes: list[str],
    confidence: str = "PROBABLE",
    alternatives: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = copy.deepcopy(base)
    result.update(
        {
            "value": value,
            "original_script": original_script,
            "confidence": confidence,
            "observation_state": "PRESENT",
            "alternatives": [] if alternatives is None else alternatives,
            "notes": notes,
        }
    )
    return result


def _patch_observations(act_no: int, observations: dict[str, Any]) -> dict[str, Any]:
    resolved = copy.deepcopy(observations)
    note = ["Coordinator-resolved by blind 2-of-3 machine consensus; confidence capped PROBABLE."]

    if act_no == 1:
        resolved["registration_date"] = _resolved(
            resolved["registration_date"],
            value={
                "julian": "1890-01-01",
                "gregorian": "1890-01-13",
                "gregorian_derived": True,
            },
            original_script="Января перваго дня",
            notes=[*note, "Only one day-word is present; Gregorian is a marked derivation."],
        )
        resolved["principal.name"] = _resolved(
            resolved["principal.name"],
            value="Ruchla Malowanczyk",
            original_script="Рухля Малованьчикъ",
            notes=note,
        )
        resolved["father.name"] = _resolved(
            resolved["father.name"],
            value="Abram Antoszewicz",
            original_script="Абрамa ... супруговъ Антошевичъ",
            notes=note,
        )
        resolved["mother.name"] = _resolved(
            resolved["mother.name"],
            value="Rifka Antoszewicz",
            original_script="Рифки, супруговъ Антошевичъ",
            notes=note,
        )
        resolved["declarants.0.name"] = _resolved(
            resolved["declarants.0.name"],
            value="Izrael Ioskowicz",
            original_script="Израель Іосковичъ",
            notes=note,
        )
        occupation_base = copy.deepcopy(resolved["declarants.1.occupation"])
        occupation_base["source_span_ids"] = ["declarants"]
        resolved["declarants.0.occupation"] = _resolved(
            occupation_base,
            value="feldsher",
            original_script="фельдшеръ",
            notes=note,
        )
        resolved["deceased_left_behind"] = _resolved(
            resolved["deceased_left_behind"],
            value={
                "mention_id": "serock-1890-death-1#survivor-0",
                "relationship": "husband",
                "name": "Cuka",
            },
            original_script="Оставивъ послѣ себя мужа Цука",
            notes=[*note, "Reader C was LEANING; value remains sub-gold."],
        )

    elif act_no == 2:
        resolved["registration_date"] = _resolved(
            resolved["registration_date"],
            value={
                "julian": "1890-01-18",
                "gregorian": "1890-01-30",
                "gregorian_derived": True,
            },
            original_script="Января восемьнадцатаго дня",
            notes=[*note, "Only one day-word is present; Gregorian is a marked derivation."],
        )
        resolved["event_date"] = _resolved(
            resolved["event_date"],
            value={
                "julian": "1890-01-17",
                "gregorian": "1890-01-29",
                "gregorian_derived": True,
                "resolved_from_relative_phrase": True,
            },
            original_script="вчерашняго числа текущаго года",
            notes=[*note, "Resolved relative to the corrected single registration date."],
        )
        resolved["principal.name"] = _resolved(
            resolved["principal.name"],
            value="Chana Auksztukalska",
            original_script="Хана Аукштукальская",
            notes=note,
        )
        resolved["mother.maiden_name"] = _resolved(
            resolved["mother.maiden_name"],
            value="Konkol",
            original_script="урожденной Конколь",
            notes=note,
        )

    elif act_no == 3:
        resolved["registration_date"] = _resolved(
            resolved["registration_date"],
            value={
                "julian": "1890-01-30",
                "gregorian": "1890-02-11",
                "gregorian_derived": True,
            },
            original_script="тридцатаго Января",
            notes=note,
        )
        resolved["event_date"] = _resolved(
            resolved["event_date"],
            value={
                "julian": "1890-01-29",
                "gregorian": "1890-02-10",
                "gregorian_derived": True,
                "resolved_from_relative_phrase": True,
            },
            original_script="вчерашняго числа",
            notes=[*note, "Resolved relative to the corrected registration date."],
        )
        resolved["principal.name"] = _resolved(
            resolved["principal.name"],
            value="Josek Zajczyk",
            original_script="Іосекъ Зайчикъ",
            notes=note,
        )
        parent = resolved.pop("father.name")
        resolved["parent.name"] = _resolved(
            parent,
            value="Szejwa Zajczyk",
            original_script="сынъ Шейвы",
            notes=[*note, "The parent role remains unresolved; do not force father or mother."],
        )
        resolved["declarants.0.name"] = _resolved(
            resolved["declarants.0.name"],
            value="Lejb Uksztukalski",
            original_script="Лейбъ Укштукальскій",
            notes=note,
        )
        resolved["declarants.1.name"] = _resolved(
            resolved["declarants.1.name"],
            value="Mortka Wolman",
            original_script="Мортка Вольманъ",
            notes=note,
        )

    elif act_no == 4:
        resolved["principal.name"] = _resolved(
            resolved["principal.name"],
            value="Pinkus Lejzor Tykulski",
            original_script="Пинкусъ Лейзоръ Тыкульскій",
            notes=note,
        )
        resolved["father.name"] = _resolved(
            resolved["father.name"],
            value="Moszka Gdala Tykulski",
            original_script="Мошка Гдали ... супруговъ Тыкульскихъ",
            notes=note,
        )
        resolved["mother.maiden_name"] = _resolved(
            resolved["mother.maiden_name"],
            value="[unclear: Psznek?]",
            original_script="[unclear: Пшнекъ?]",
            confidence="UNCLEAR",
            alternatives=[{"value": "Psznek", "original_script": "Пшнекъ"}],
            notes=[*note, "Internal letters remain cramped."],
        )
        resolved["declarants.0.name"] = _resolved(
            resolved["declarants.0.name"],
            value="[unclear: Josek Psznek?]",
            original_script="[unclear: Іосекъ Пшнекъ?]",
            confidence="UNCLEAR",
            alternatives=[{"value": "Josek Psznek", "original_script": "Іосекъ Пшнекъ"}],
            notes=[*note, "Surname matches the mother's née-name word-shape; internal letters remain cramped."],
        )
        resolved["declarants.1.name"] = _resolved(
            resolved["declarants.1.name"],
            value="Berk Kaltun",
            original_script="Беркъ Калтунъ",
            notes=note,
        )
        resolved["declarants.1.occupation"] = _resolved(
            resolved["declarants.1.occupation"],
            value="attendant",
            original_script="служитель",
            notes=note,
        )

    elif act_no == 5:
        resolved["principal.name"] = _resolved(
            resolved["principal.name"],
            value="Chil Welwel Cykor",
            original_script="Хиль Вельвель Цикоръ",
            notes=note,
        )
        resolved["father.name"] = _resolved(
            resolved["father.name"],
            value="Chaim Jankel Cykor",
            original_script="сынъ Хаима Янкеля",
            notes=note,
        )

    return dict(sorted(resolved.items()))


def build_record(act_no: int) -> dict[str, Any]:
    """Build one deterministic materialized record from Reader B plus resolved corrections."""
    if act_no not in range(1, 6):
        raise ValueError("only coordinator-approved acts 1-5 may be materialized")
    source_path = ROOT / "labels" / "readerB" / f"serock-1890-death-{act_no}.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    wave = 1 if act_no <= 2 else 2
    consensus, arbitration = WAVES[wave]
    return {
        "$schema": "../../schemas/silver-record-1.0.0.schema.json",
        "schema_version": "1.0.0",
        "record_id": source["record_id"],
        "tier": "SILVER",
        "clerk_year": source["clerk_year"],
        "artifact": source["artifact"],
        "target": source["target"],
        "source_spans": source["source_spans"],
        "observations": _patch_observations(act_no, source["observations"]),
        "resolution": {
            "method": "BLIND_2_OF_3_MACHINE_CONSENSUS",
            "confidence_cap": "PROBABLE",
            "consensus_document": _source(consensus),
            "arbitration_document": _source(arbitration),
        },
        "authority_warning": AUTHORITY_WARNING,
    }


def build_records() -> list[dict[str, Any]]:
    """Build all and only the coordinator-approved wave 001-002 silver records."""
    return [build_record(act_no) for act_no in range(1, 6)]


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    records = build_records()
    for record in records:
        path = OUTPUT_DIR / f"{record['record_id']}.json"
        path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps({"materialized": len(records), "output_dir": str(OUTPUT_DIR)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
