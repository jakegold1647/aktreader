import hashlib
from pathlib import Path

import pytest

from aktreader.briefs import BriefGenerationError, build_reader_briefs


def _spec(tmp_path: Path) -> dict[str, object]:
    first = tmp_path / "01-02.jpg"
    second = tmp_path / "03-04.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    return {
        "schema_version": "1.0.0",
        "created_at": "2026-07-28T22:30:00-04:00",
        "register_unit": {
            "unit_id": "UMZ-1900",
            "fond": "73/826/0",
            "town": "Serock",
            "year": 1900,
            "act_type": "death",
            "language": "ru",
            "clerk_year_id": "73-826-0|serock|1900|clerk-unknown",
        },
        "act_range": {"start": 1, "end": 4},
        "artifacts": [
            {
                "act_start": 1,
                "act_end": 2,
                "path": str(first),
                "sha256": hashlib.sha256(b"first").hexdigest(),
                "width_px": 100,
                "height_px": 80,
                "page_index": 0,
            },
            {
                "act_start": 3,
                "act_end": 4,
                "path": str(second),
                "sha256": hashlib.sha256(b"second").hexdigest(),
                "width_px": 120,
                "height_px": 90,
                "page_index": 0,
            },
        ],
        "prompt": {
            "version": "1.4.0",
            "sha256": "a" * 64,
            "path": "prompts/reader_prompt.md",
        },
        "readers": {
            "A": {
                "reader_id": "reader-a",
                "reader_family": "family-a",
                "reader_version": "a-1",
                "mode": "subscription_session",
            },
            "B": {
                "reader_id": "reader-b",
                "reader_family": "family-b",
                "reader_version": "b-1",
                "mode": "subscription_session",
            },
        },
    }


def test_wave_generator_emits_matching_blind_paired_briefs(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    first = build_reader_briefs(spec)
    second = build_reader_briefs(spec)

    assert first == second
    assert len(first["reader_a"]) == len(first["reader_b"]) == 4
    assert first["blind_group_id"].startswith("blind-umz-1900-1-4-")
    for left, right in zip(first["reader_a"], first["reader_b"], strict=True):
        assert left["record_id"] == right["record_id"]
        assert left["target"] == right["target"]
        assert left["artifact"] == right["artifact"]
        assert left["prompt"] == right["prompt"]
        assert left["reader"]["reader_id"] != right["reader"]["reader_id"]
        assert left["reader"]["blind_group_id"] == right["reader"]["blind_group_id"]
        assert left["reader"]["other_reader_output_seen"] is False
        assert right["reader"]["other_reader_output_seen"] is False


def test_wave_generator_rejects_artifact_hash_drift(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    spec["artifacts"][0]["sha256"] = "0" * 64

    with pytest.raises(BriefGenerationError, match="mismatch"):
        build_reader_briefs(spec)


def test_wave_generator_accepts_blind_same_family_sessions_with_limitation(
    tmp_path: Path,
) -> None:
    spec = _spec(tmp_path)
    spec["readers"]["B"]["reader_family"] = "family-a"

    briefs = build_reader_briefs(spec)

    assert briefs["independence"] == {
        "distinct_reader_ids": True,
        "distinct_model_families": False,
        "correlated_blind_spots_possible": True,
    }
