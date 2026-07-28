"""Build the machine-readable silver/quarantine tier index from frozen wave artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "labels" / "silver" / "manifest.json"
SCHEMA = ROOT / "schemas" / "silver-tier-manifest-1.0.0.schema.json"
PROMPT_V1_SHA256 = "88e56abd110b1f206a2d4cf0d699fbd449e667ea810ae1854a0c6a8d63269d82"
CLERK_YEAR_ID = "73-826-0|serock|1890|clerk-unknown"
AUTHORITY_WARNING = "extraction is not authority — verify against the scan"
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
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source(path: str) -> dict[str, str]:
    absolute = ROOT / path
    if not absolute.is_file():
        raise FileNotFoundError(f"required frozen source is missing: {path}")
    return {"path": path, "sha256": _sha256(absolute)}


def _provenance(act_no: int, wave: int) -> dict[str, Any]:
    consensus_path, arbitration_path = WAVES[wave]
    return {
        "source_labels": [
            {
                "reader_role": "A",
                **_source(f"labels/readerA/serock-1890-death-{act_no}.json"),
            },
            {
                "reader_role": "B",
                **_source(f"labels/readerB/serock-1890-death-{act_no}.json"),
            },
        ],
        "consensus_document": _source(consensus_path),
        "arbitration_document": _source(arbitration_path),
        "reader_a_prompt_binding": "PROVENANCE_ERRATA_UNVERIFIED",
        "reader_b_prompt_sha256": PROMPT_V1_SHA256,
    }


def build_manifest() -> dict[str, Any]:
    """Return the deterministic tier index; resolved field payloads remain source-addressed."""
    records = []
    for act_no in range(1, 6):
        wave = 1 if act_no <= 2 else 2
        provenance = _provenance(act_no, wave)
        consensus = provenance["consensus_document"]
        records.append(
            {
                "record_id": f"serock-1890-death-{act_no}",
                "tier": "SILVER",
                "clerk_year_id": CLERK_YEAR_ID,
                "resolution_method": "BLIND_2_OF_3_MACHINE_CONSENSUS",
                "confidence_cap": "PROBABLE",
                "training_eligible": True,
                "training_materialized": False,
                "eval_eligible": False,
                "human_verified": False,
                "resolved_fields": {
                    "storage": "COORDINATOR_RESOLVED_APPENDIX",
                    **consensus,
                },
                "provenance": provenance,
            }
        )
    return {
        "$schema": "../../schemas/silver-tier-manifest-1.0.0.schema.json",
        "schema_version": "1.0.0",
        "created_on": "2026-07-28",
        "tier_definition": {
            "name": "SILVER",
            "basis": "BLIND_2_OF_3_MACHINE_CONSENSUS",
            "training_eligible": True,
            "eval_eligible": False,
            "human_verified": False,
        },
        "records": records,
        "quarantine": [
            {
                "record_id": "serock-1890-death-6",
                "tier": None,
                "status": "HUMAN_VERIFICATION_REQUIRED",
                "training_eligible": False,
                "eval_eligible": False,
                "human_verified": False,
                "reason": (
                    "Identity-level fork resolved only by machine 2-of-3; the standing "
                    "protocol requires a sampled human check before tier assignment."
                ),
                "provenance": _provenance(6, 2),
            }
        ],
        "restricted_sources_used": False,
        "authority_warning": AUTHORITY_WARNING,
    }


def main() -> int:
    payload = build_manifest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"silver": len(payload["records"]), "quarantined": 1}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
