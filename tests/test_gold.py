import json
from pathlib import Path

from aktreader.gold import load_gold_records, sha256_file, validate_corpus

ROOT = Path(__file__).resolve().parents[1]


def test_gold_corpus_contract_and_coverage() -> None:
    records = load_gold_records(ROOT)
    coverage = validate_corpus(records)

    assert coverage["total"] == 36
    assert coverage["towns"] == {"Pułtusk": 7, "Serock": 29}
    assert coverage["act_types"] == {"birth": 13, "death": 18, "marriage": 5}
    assert coverage["languages"] == {"ru": 36}
    assert coverage["clerk_years"] > 0
    assert all(record["register"]["clerk_year"]["id"] for record in records)


def test_manifest_matches_validated_corpus() -> None:
    records = load_gold_records(ROOT)
    coverage = validate_corpus(records)
    manifest = json.loads((ROOT / "gold" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["coverage"] == coverage
    assert manifest["known_gaps"][0]["target"] == "Polish-language acts"
    assert manifest["restricted_sources_used"] is False


def test_spot_check_manifest_names_five_existing_records() -> None:
    record_ids = {record["record_id"] for record in load_gold_records(ROOT)}
    spot_checks = json.loads((ROOT / "gold" / "spot_check.json").read_text(encoding="utf-8"))

    assert len(spot_checks["records"]) == 5
    assert {item["record_id"] for item in spot_checks["records"]}.issubset(record_ids)


def test_all_gold_clerk_years_are_permanently_sequestered() -> None:
    records = load_gold_records(ROOT)
    holdout = json.loads((ROOT / "gold" / "clerk_year_holdout.json").read_text(encoding="utf-8"))
    record_clerk_years = {record["register"]["clerk_year"]["id"] for record in records}

    assert set(holdout["holdout_clerk_year_ids"]) == record_clerk_years
    assert set(holdout["record_ids"]) == {record["record_id"] for record in records}
    assert holdout["training_overlap_allowed"] is False


def test_identity_fork_is_quarantined_outside_gold_pending_human_review() -> None:
    manifest = json.loads((ROOT / "gold" / "manifest.json").read_text(encoding="utf-8"))
    records = load_gold_records(ROOT)
    quarantine = manifest["quarantine"]

    assert quarantine == [
        {
            "record_id": "serock-1890-death-6",
            "status": "HUMAN_VERIFICATION_REQUIRED",
            "gold_ingest_allowed": False,
            "reason": (
                "Identity-level Reader A/Reader B fork resolved only by third-reader "
                "2-of-3 consensus; sampled human verification is still mandatory."
            ),
            "source": (
                "labels/consensus/"
                "serock-1890-deaths-3-6_wave002_CONSENSUS.md#wave-002-resolved"
            ),
        }
    ]
    assert quarantine[0]["record_id"] not in {record["record_id"] for record in records}


def test_gold_act_files_contain_no_restricted_source_provenance() -> None:
    forbidden = ("yad vashem", "ushmm", "arolsen")

    for path in (ROOT / "gold" / "acts").glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        assert all(term not in text for term in forbidden), path.name


def test_recorded_source_and_artifact_checksums_match_disk() -> None:
    for record in load_gold_records(ROOT):
        source_note = Path(record["provenance"]["source_note"])
        assert source_note.is_file()
        assert sha256_file(source_note) == record["provenance"]["source_note_sha256"]

        if record["artifact"]["status"] == "LOCAL":
            artifact = Path(record["artifact"]["path"])
            assert artifact.is_file()
            assert sha256_file(artifact) == record["artifact"]["sha256"]
