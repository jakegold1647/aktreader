"""Build the no-fetch acquisition want-list for NOT_LOCALIZED gold records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "examples" / "p2-baseline.want-list.json"
KATALOG = {"birth": 1, "marriage": 2, "death": 3}
SOURCE_OBJECT_415 = {
    "serock-1882-birth-2",
    "serock-1899-birth-5",
    "serock-1899-birth-6",
    "serock-1902-marriage-3",
    "serock-1903-marriage-23",
}


def _serock_file_range(act_no: int) -> str:
    if act_no < 1:
        raise ValueError("act number must be positive")
    if act_no <= 2:
        return "01-02"
    first = 3 + 4 * ((act_no - 3) // 4)
    return f"{first:02d}-{first + 3:02d}"


def build_want_list() -> dict[str, Any]:
    wants = []
    for path in sorted((ROOT / "gold" / "acts").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["artifact"]["status"] != "NOT_LOCALIZED":
            continue
        register = record["register"]
        common = {
            "record_id": record["record_id"],
            "register": {
                "fond": register["fond"],
                "town": register["town"],
                "year": register["year"],
                "act_type": register["act_type"],
                "act_no": register["act_no"],
            },
        }
        if register["fond"] == "73/826/0":
            if record["record_id"] not in SOURCE_OBJECT_415:
                raise ValueError(
                    "unclassified Serock acquisition gap: "
                    f"{record['record_id']}; assign an explicit fail-closed reason"
                )
            unit_year = 1900 if register["year"] == 1902 else register["year"]
            katalog = KATALOG[register["act_type"]]
            file_range = _serock_file_range(register["act_no"])
            wants.append(
                {
                    **common,
                    "status": "NOT_LOCALIZED",
                    "reason": "SOURCE_OBJECT_415",
                    "skanoteka": {
                        "zespol_id": 318,
                        "code": "0826d",
                        "unit": f"UMZ-{unit_year}",
                        "sy": unit_year,
                        "katalog": katalog,
                        "file_range": file_range,
                        "filename": f"{file_range}.jpg",
                        "viewer_url": (
                            "https://skanoteka.genealodzy.pl/index.php"
                            f"?op=pg&id=318&sy={unit_year}&kt={katalog}"
                            f"&plik={file_range}.jpg"
                        ),
                    },
                    "notes": [
                        *(
                            ["The sy=1900 unit physically contains the 1902 register."]
                            if register["year"] == 1902
                            else []
                        ),
                        (
                            "The exact Skanoteka download object returned HTTP 415 after one "
                            "fresh-viewer retry; keep fail-closed pending a later retry or "
                            "maintainer repair."
                        ),
                    ],
                }
            )
        else:
            wants.append(
                {
                    **common,
                    "status": "COLLECTION_MAPPING_REQUIRED",
                    "skanoteka": None,
                    "notes": [
                        "Fond 84 is Pułtusk, not Serock zespół 318/0826d.",
                        "Do not invent a unit or file range; owner/coordinator must supply the Pułtusk catalogue mapping.",
                    ],
                }
            )
    return {
        "schema_version": "1.0.0",
        "created_on": "2026-07-28",
        "purpose": "owner-fetched expansion of the scan-backed P2 baseline ceiling",
        "network_actions_performed": False,
        "source_layout": {
            "zespol_id": 318,
            "code": "0826d",
            "category_map": KATALOG,
            "range_rule": "01-02, then four-act files 03-06, 07-10, ...",
            "known_exception": "actual 1902 register is catalogued under sy=1900",
        },
        "summary": {
            "not_localized_total": len(wants),
            "ready_for_owner_fetch": sum(
                want["status"] == "READY_FOR_OWNER_FETCH" for want in wants
            ),
            "source_object_415": sum(
                want.get("reason") == "SOURCE_OBJECT_415" for want in wants
            ),
            "collection_mapping_required": sum(
                want["status"] == "COLLECTION_MAPPING_REQUIRED" for want in wants
            ),
        },
        "records": wants,
    }


def main() -> int:
    payload = build_want_list()
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
