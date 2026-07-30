"""Mechanical intake validation for paid blind human transcriptions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import jsonschema


class HumanGoldSubmissionError(ValueError):
    """Raised when a paid transcription cannot enter adjudication."""


def validate_human_transcription(
    payload: Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    qualification: bool = False,
) -> None:
    """Validate schema, exact line count, encoding, and qualification independence."""
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
            payload
        )
    except jsonschema.ValidationError as error:
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        raise HumanGoldSubmissionError(f"{location}: {error.message}") from error

    transcription = payload["transcription"]["original_script"]
    if "\ufffd" in transcription:
        raise HumanGoldSubmissionError("transcription contains Unicode replacement characters")
    actual_lines = len(transcription.splitlines())
    if actual_lines != payload["transcription"]["line_count"]:
        raise HumanGoldSubmissionError(
            f"transcription.line_count is {payload['transcription']['line_count']}; "
            f"actual line count is {actual_lines}"
        )

    worker = payload["worker"]
    if qualification and worker["machine_assistance_used"]:
        raise HumanGoldSubmissionError(
            "qualification submissions must not use OCR or AI assistance"
        )
    if worker["machine_assistance_used"] and not worker["machine_assistance_detail"]:
        raise HumanGoldSubmissionError(
            "machine_assistance_detail is required when assistance was used"
        )
