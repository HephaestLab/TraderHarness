"""Offline replacement of company aliases with stable entity templates."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

import pandas as pd
from flashtext import KeywordProcessor

from traderharness.data.stock_registry_loader import is_a_share_stock_code


def _is_plausible_alias(alias: str, registered_name: str) -> bool:
    """Reject cross-market code collisions while retaining normal abbreviations."""
    if alias == registered_name or alias in registered_name or registered_name in alias:
        return True
    alias_pairs = {alias[index : index + 2] for index in range(len(alias) - 1)}
    return any(pair in registered_name for pair in alias_pairs)


def filter_a_share_announcements(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep raw six-digit A-share announcement codes without coercing width."""
    if "stock_code" not in frame.columns:
        raise KeyError("stock_code")
    mask = frame["stock_code"].astype(str).map(is_a_share_stock_code)
    return frame.loc[mask].reset_index(drop=True)


class EntityTemplateMap:
    """Replace known aliases with ``{{C<real-code>}}`` placeholders."""

    def __init__(self, aliases: Mapping[str, Iterable[str]]) -> None:
        candidates: dict[str, set[str]] = defaultdict(set)
        for code, values in aliases.items():
            normalized_code = str(code).zfill(6)
            for value in values:
                alias = str(value).strip()
                if len(alias) >= 2 and alias != normalized_code:
                    candidates[alias].add(normalized_code)

        # Ambiguous aliases must not be assigned arbitrarily.
        self._alias_to_code = {
            alias: next(iter(codes)) for alias, codes in candidates.items() if len(codes) == 1
        }
        self._processor = KeywordProcessor(case_sensitive=True)
        # Chinese stock names are commonly followed directly by digits
        # (for example "必得科技3连板"). FlashText treats digits as word
        # characters by default and would otherwise miss these entities.
        self._processor.non_word_boundaries = set()
        for alias, code in self._alias_to_code.items():
            self._processor.add_keyword(alias, f"{{{{C{code}}}}}")

    def template_text(self, value):
        if not isinstance(value, str):
            return value
        return self._processor.replace_keywords(value)

    def template_frame(self, frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
        out = frame.copy()
        for column in columns:
            if column in out.columns:
                out[column] = out[column].map(self.template_text)
        return out


def build_alias_map(
    registry: Mapping[str, Mapping],
    announcements: pd.DataFrame | None = None,
) -> dict[str, set[str]]:
    """Combine registry names with observed announcement stock names."""
    aliases: dict[str, set[str]] = defaultdict(set)
    for code, info in registry.items():
        name = str(info.get("name", "")).strip()
        if name:
            aliases[str(code).zfill(6)].add(name)

    if (
        announcements is not None
        and not announcements.empty
        and {"stock_code", "stock_name"}.issubset(announcements.columns)
    ):
        registry_codes = set(aliases)
        for code, name in announcements[["stock_code", "stock_name"]].itertuples(index=False):
            if pd.isna(code) or pd.isna(name):
                continue
            raw_code = str(code).strip()
            if not is_a_share_stock_code(raw_code):
                continue
            normalized_code = raw_code
            if normalized_code not in registry_codes:
                continue
            text = str(name).strip()
            registered_name = str(registry.get(normalized_code, {}).get("name", "")).strip()
            if text and _is_plausible_alias(text, registered_name):
                aliases[normalized_code].add(text)
    return dict(aliases)
