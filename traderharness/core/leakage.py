"""Static checks for identity/date leakage in masked Agent-visible text."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class LeakageFinding:
    kind: str
    value: str
    location: str = ""


class EntityLeakDetector:
    """Find real aliases, absolute dates, and unresolved entity templates."""

    # Require an explicit month marker (月) or ISO separators. Bare forms like
    # "2023年1万亿元" (amount, not a calendar month) must not be flagged.
    _date_pattern = re.compile(
        r"(?<!\d)20\d{2}年(?:1[0-2]|0?[1-9])月(?:(?:3[01]|[12]\d|0?[1-9])日?)?"
        r"|(?<!\d)20\d{2}[-/](?:1[0-2]|0?[1-9])(?:[-/](?:3[01]|[12]\d|0?[1-9]))?(?!\d)"
    )
    _month_day_pattern = re.compile(
        r"(?<![\d年])(?:1[0-2]|0?[1-9])月(?:3[01]|[12]\d|0?[1-9])日"
    )
    _template_pattern = re.compile(r"\{\{C\d{6}\}\}")

    def __init__(self, aliases: Mapping[str, Iterable[str]]) -> None:
        values = {
            str(alias).strip()
            for code_aliases in aliases.values()
            for alias in code_aliases
            if len(str(alias).strip()) >= 2
        }
        escaped = sorted((re.escape(value) for value in values), key=len, reverse=True)
        self._alias_pattern = re.compile("|".join(escaped)) if escaped else None

    def scan_text(self, text: str, *, location: str = "") -> list[LeakageFinding]:
        findings: list[LeakageFinding] = []
        if self._alias_pattern is not None:
            findings.extend(
                LeakageFinding("entity_alias", match.group(0), location)
                for match in self._alias_pattern.finditer(text)
            )
        findings.extend(
            LeakageFinding("calendar_date", match.group(0), location)
            for match in self._date_pattern.finditer(text)
        )
        findings.extend(
            LeakageFinding("calendar_date", match.group(0), location)
            for match in self._month_day_pattern.finditer(text)
        )
        findings.extend(
            LeakageFinding("template", match.group(0), location)
            for match in self._template_pattern.finditer(text)
        )
        return findings
