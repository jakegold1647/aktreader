"""The clerk-year reservation table must keep matching the holdout it describes.

TRAINING_CORPUS_PLAN.md tells a wave planner which Serock clerk-years are
evaluation-sequestered and which are open for training reads. That table is
prose, so nothing stops it drifting away from gold/clerk_year_holdout.json,
which is the actual authority. A drifted table would send a wave into a
sequestered year and produce zero training-eligible records - the failure the
table exists to prevent.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "TRAINING_CORPUS_PLAN.md"
HOLDOUT = ROOT / "gold" / "clerk_year_holdout.json"

_ROW = re.compile(r"^\|\s*(\d{4})\s*\|\s*(SEQUESTERED|OPEN)\s*\|")


def _table_rows() -> dict[int, str]:
    rows: dict[int, str] = {}
    for line in PLAN.read_text(encoding="utf-8").splitlines():
        if match := _ROW.match(line.strip()):
            rows[int(match.group(1))] = match.group(2)
    return rows


def _sequestered_serock_years() -> set[int]:
    payload = json.loads(HOLDOUT.read_text(encoding="utf-8"))
    years: set[int] = set()
    for clerk_year_id in payload["holdout_clerk_year_ids"]:
        parts = clerk_year_id.split("|")
        if len(parts) >= 3 and parts[1] == "serock" and parts[2].isdigit():
            years.add(int(parts[2]))
    return years


def test_reservation_table_is_present_and_parsed() -> None:
    rows = _table_rows()
    assert rows, "no clerk-year reservation rows found in TRAINING_CORPUS_PLAN.md"
    assert _sequestered_serock_years(), "no Serock clerk-years found in the holdout"


def test_every_table_sequestered_year_is_actually_held_out() -> None:
    holdout_years = _sequestered_serock_years()
    claimed = {year for year, status in _table_rows().items() if status == "SEQUESTERED"}
    assert not (claimed - holdout_years), (
        "TRAINING_CORPUS_PLAN.md calls these Serock years sequestered, but "
        f"gold/clerk_year_holdout.json does not list them: {sorted(claimed - holdout_years)}"
    )


def test_no_table_open_year_is_secretly_held_out() -> None:
    holdout_years = _sequestered_serock_years()
    claimed_open = {year for year, status in _table_rows().items() if status == "OPEN"}
    leaked = claimed_open & holdout_years
    assert not leaked, (
        "TRAINING_CORPUS_PLAN.md offers these Serock years for training reads, but they are "
        f"evaluation-sequestered in gold/clerk_year_holdout.json: {sorted(leaked)}"
    )


def test_table_covers_every_sequestered_serock_year() -> None:
    rows = _table_rows()
    missing = _sequestered_serock_years() - set(rows)
    assert not missing, (
        "these Serock clerk-years are sequestered but absent from the reservation table, "
        f"so a wave planner reading the table would not see them: {sorted(missing)}"
    )
