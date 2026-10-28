"""Explicit recorded-response provider for offline development tests, never AI evidence."""

from __future__ import annotations

import json
from pathlib import Path

from .intake import IntakeConfigurationError, IntakeUnavailable, Interpretation


class RecordedFixtureInterpreter:
    """Implements Interpreter using a caller-supplied development fixture file.

    This provider is deliberately not a runtime intake mode or evaluation profile.
    Missing records fail instead of guessing or silently invoking a real model.
    """

    def __init__(self, path: Path):
        fixture = json.loads(Path(path).read_text())
        if fixture.get("mode") != "recorded-fixture" or fixture.get("schema_version") != 1:
            raise IntakeConfigurationError("Recorded fixture needs an explicit fixture mode and schema")
        self.records: dict[str, Interpretation] = {}
        for row in fixture["records"]:
            text = row["text"]
            result = Interpretation.model_validate(row["interpretation"])
            if (
                not isinstance(text, str)
                or text in self.records
                or result.mode != "recorded-fixture"
                or result.needs_clarification != (result.intent == "unknown")
            ):
                raise IntakeConfigurationError("Invalid, duplicated or incorrectly labeled recorded fixture")
            self.records[text] = result

    def interpret(self, text: str) -> Interpretation:
        try:
            return self.records[text]
        except KeyError:
            raise IntakeUnavailable("No recorded fixture for this exact development input") from None
