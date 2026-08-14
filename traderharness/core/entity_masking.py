"""Run-scoped company anonymization for contamination-resistant backtests.

The engine continues to use real stock codes internally. Agent-facing egress
uses a deterministic permutation within each exchange/board bucket, preserving
market-rule semantics while breaking the association between identity and
historical data. Names and aliases are replaced with neutral labels.
"""

from __future__ import annotations

import random
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd


class EntityMasker:
    """Deterministic, reversible stock-code and company-name masker."""

    def __init__(
        self,
        codes: Iterable[str],
        *,
        names: Mapping[str, str] | None = None,
        aliases: Mapping[str, Iterable[str]] | None = None,
        sanitize_aliases: Mapping[str, Iterable[str]] | None = None,
        seed: int | str = 0,
        enabled: bool = True,
        style: str = "permutation",
    ) -> None:
        self.enabled = enabled
        if style not in {"permutation", "opaque"}:
            raise ValueError("entity mask style must be 'permutation' or 'opaque'")
        self.style = style
        normalized = sorted({str(code).zfill(6) for code in codes})
        self._real_to_masked = (
            self._build_opaque_mapping(normalized, seed)
            if style == "opaque"
            else self._build_mapping(normalized, seed)
        )
        self._masked_to_real = {masked: real for real, masked in self._real_to_masked.items()}

        self._names = {str(code).zfill(6): str(name) for code, name in (names or {}).items()}
        self._alias_to_code = self._build_alias_to_code(self._names, aliases)
        # Broader map used only when scrubbing model-generated text. Keeping it
        # separate from `_alias_to_code` preserves point-in-time egress masking
        # (and therefore replay fingerprints) when historical announcement
        # aliases are loaded for hallucination scrubbing.
        self._sanitize_alias_to_code = dict(self._alias_to_code)
        if sanitize_aliases is not None:
            self._sanitize_alias_to_code.update(
                self._build_alias_to_code({}, sanitize_aliases)
            )
            # Registry display names always win for sanitize lookups too.
            for code, name in self._names.items():
                if name and name != code:
                    self._sanitize_alias_to_code[name] = code

        self._alias_re = self._compile_alias_re(self._alias_to_code)
        self._sanitize_re = self._compile_alias_re(self._sanitize_alias_to_code)
        code_patterns = sorted((re.escape(c) for c in normalized), key=len, reverse=True)
        self._code_re = (
            re.compile(r"(?<!\d)(?:" + "|".join(code_patterns) + r")(?!\d)")
            if code_patterns
            else None
        )
        self._template_re = re.compile(r"\{\{C(\d{6})\}\}")
        self._neutral_re = re.compile(r"公司-([A-Z]+-[A-Z0-9]+|\d{6})")
        masked_code_patterns = sorted(
            (re.escape(c) for c in self._masked_to_real), key=len, reverse=True
        )
        self._masked_code_re = (
            re.compile(
                r"(?<![A-Za-z0-9-])(?:"
                + "|".join(masked_code_patterns)
                + r")(?![A-Za-z0-9-])"
            )
            if masked_code_patterns
            else None
        )

    @staticmethod
    def _build_alias_to_code(
        names: Mapping[str, str],
        aliases: Mapping[str, Iterable[str]] | None,
    ) -> dict[str, str]:
        alias_to_code: dict[str, str] = {}
        for code, name in names.items():
            if name and name != code:
                alias_to_code[name] = str(code).zfill(6)
        for code, values in (aliases or {}).items():
            normalized_code = str(code).zfill(6)
            for alias in values:
                text = str(alias).strip()
                if text and text != normalized_code and not text.startswith("{{C"):
                    alias_to_code[text] = normalized_code
        return alias_to_code

    @staticmethod
    def _compile_alias_re(alias_to_code: Mapping[str, str]) -> re.Pattern | None:
        alias_patterns = sorted((re.escape(a) for a in alias_to_code), key=len, reverse=True)
        return re.compile("|".join(alias_patterns)) if alias_patterns else None

    @staticmethod
    def board_key(code: str) -> str:
        """Bucket codes so their masked counterpart keeps the same market rules."""
        code = str(code).zfill(6)
        if code.startswith(("688", "689")):
            return "sh_star"
        if code.startswith(("300", "301")):
            return "sz_chinext"
        if code.startswith(("4", "8", "920")):
            return "bse"
        if code.startswith(("6", "9")):
            return "sh_main"
        return "sz_main"

    @classmethod
    def _build_mapping(cls, codes: list[str], seed: int | str) -> dict[str, str]:
        groups: dict[str, list[str]] = defaultdict(list)
        for code in codes:
            groups[cls.board_key(code)].append(code)

        mapping: dict[str, str] = {}
        for board, members in groups.items():
            members.sort()
            if len(members) == 1:
                mapping[members[0]] = members[0]
                continue
            rng = random.Random(f"{seed}:{board}")
            shift = rng.randrange(1, len(members))
            rotated = members[shift:] + members[:shift]
            mapping.update(zip(members, rotated, strict=True))
        return mapping

    @classmethod
    def _build_opaque_mapping(cls, codes: list[str], seed: int | str) -> dict[str, str]:
        """Build reversible aliases that cannot be mistaken for real stock codes."""
        prefixes = {
            "sh_main": "SHM",
            "sz_main": "SZM",
            "sz_chinext": "GEM",
            "sh_star": "STAR",
            "bse": "BSE",
        }
        groups: dict[str, list[str]] = defaultdict(list)
        for code in codes:
            groups[cls.board_key(code)].append(code)

        mapping: dict[str, str] = {}
        for board, members in sorted(groups.items()):
            members.sort()
            rng = random.Random(f"{seed}:{board}:opaque")
            tokens = list(range(1, len(members) + 1))
            rng.shuffle(tokens)
            prefix = prefixes[board]
            for code, token in zip(members, tokens, strict=True):
                mapping[code] = f"{prefix}-{token:06d}"
        return mapping

    @property
    def real_to_masked(self) -> dict[str, str]:
        return dict(self._real_to_masked)

    @property
    def masked_to_real(self) -> dict[str, str]:
        return dict(self._masked_to_real)

    def mask_code(self, code: Any) -> Any:
        if not self.enabled or code is None:
            return code
        text = str(code).zfill(6)
        return self._real_to_masked.get(text, code)

    def unmask_code(self, code: Any) -> Any:
        if not self.enabled or code is None:
            return code
        text = str(code).zfill(6)
        if self.style == "opaque" and re.fullmatch(r"\d{6}", text):
            candidates = self.masked_code_candidates(text)
            if len(candidates) == 1:
                return self._masked_to_real[candidates[0]]
        return self._masked_to_real.get(text, code)

    def masked_code_candidates(self, code: Any) -> list[str]:
        """Return full opaque aliases matching a model-supplied numeric suffix."""
        if not self.enabled or self.style != "opaque" or code is None:
            return []
        text = str(code).strip()
        if not re.fullmatch(r"\d{1,6}", text):
            return []
        suffix = text.zfill(6)
        return sorted(
            masked for masked in self._masked_to_real if masked.endswith("-" + suffix)
        )

    def mask_name(self, real_code: str) -> str:
        """Return a neutral label tied to the run-scoped masked code."""
        return f"公司-{self.mask_code(real_code)}"

    def sanitize_agent_text(self, value: Any) -> Any:
        """Remove generated real aliases without remapping Agent-visible codes."""
        if not self.enabled or not isinstance(value, str):
            return value
        text = value
        if self._sanitize_re is not None:
            text = self._sanitize_re.sub(
                lambda match: self.mask_name(self._sanitize_alias_to_code[match.group(0)]),
                text,
            )
        text = self._template_re.sub(
            lambda match: self.mask_name(match.group(1)),
            text,
        )
        # Legacy egress represented an alias outside the loaded universe as
        # 公司-<canonical code>. Keep mask_name replay-compatible, then remove
        # that residual identity only on the live sanitization pass. A valid
        # in-universe neutral label always contains a code in _masked_to_real.
        return self._neutral_re.sub(
            lambda match: (
                match.group(0) if match.group(1) in self._masked_to_real else "外部公司"
            ),
            text,
        )

    def sanitize_agent_obj(self, value: Any) -> Any:
        if not self.enabled:
            return value
        if isinstance(value, str):
            return self.sanitize_agent_text(value)
        if isinstance(value, dict):
            return {key: self.sanitize_agent_obj(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.sanitize_agent_obj(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.sanitize_agent_obj(item) for item in value)
        return value

    def mask_text(self, value: Any) -> Any:
        if not self.enabled or not isinstance(value, str):
            return value
        text = value
        neutral_values: list[str] = []
        template_values: list[str] = []

        def hold_neutral(match: re.Match) -> str:
            if match.group(1) not in self._masked_to_real:
                return match.group(0)
            token = f"\ufff2{len(neutral_values)}\ufff3"
            neutral_values.append(match.group(0))
            return token

        def hold_template(match: re.Match) -> str:
            token = f"\ufff0{len(template_values)}\ufff1"
            template_values.append(self.mask_name(match.group(1)))
            return token

        text = self._neutral_re.sub(hold_neutral, text)
        text = self._template_re.sub(hold_template, text)
        # Replace codes first. Alias replacements contain the masked code in
        # their neutral label and must not be fed through the permutation again.
        if self._code_re is not None:
            text = self._code_re.sub(lambda match: str(self.mask_code(match.group(0))), text)
        if self._alias_re is not None:
            text = self._alias_re.sub(
                lambda match: self.mask_name(self._alias_to_code[match.group(0)]),
                text,
            )
        for index, replacement in enumerate(template_values):
            text = text.replace(f"\ufff0{index}\ufff1", replacement)
        for index, replacement in enumerate(neutral_values):
            text = text.replace(f"\ufff2{index}\ufff3", replacement)
        return text

    def mask_df(self, df: pd.DataFrame, code_col: str = "stock_code") -> pd.DataFrame:
        """Return an entity-masked copy of an Agent-facing DataFrame."""
        if not self.enabled:
            return df
        out = df.copy()
        if code_col in out.columns:
            out[code_col] = out[code_col].map(self.mask_code)
        for column in out.columns:
            if column == code_col:
                continue
            if pd.api.types.is_object_dtype(out[column]) or pd.api.types.is_string_dtype(
                out[column]
            ):
                out[column] = out[column].map(self.mask_text)
        return out

    def unmask_obj(self, value: Any) -> Any:
        """Reverse exact masked codes in nested tool-call arguments."""
        if not self.enabled:
            return value
        if isinstance(value, str):
            # Tool arguments are Agent-authored and therefore live in the
            # pseudocode namespace. Restore embedded pseudocodes too, not just
            # a string that consists solely of one code. Otherwise order
            # reasoning is stored with a pseudocode and gets permuted again
            # when the final result artifact masks canonical engine state.
            return self.reveal_text(value)
        if isinstance(value, dict):
            return {key: self.unmask_obj(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.unmask_obj(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.unmask_obj(item) for item in value)
        return value

    def reveal_text(self, value: Any) -> Any:
        """Restore model-visible pseudocodes and neutral labels for local review."""
        if not self.enabled or not isinstance(value, str):
            return value
        text = value
        neutral_values: list[str] = []

        def hold_neutral(match: re.Match) -> str:
            masked_code = match.group(1)
            real_code = self._masked_to_real.get(masked_code)
            if real_code is None:
                return match.group(0)
            token = f"\ufff4{len(neutral_values)}\ufff5"
            neutral_values.append(self._names.get(real_code, real_code))
            return token

        text = self._neutral_re.sub(hold_neutral, text)
        if self._masked_code_re is not None:
            text = self._masked_code_re.sub(
                lambda match: self._masked_to_real.get(match.group(0), match.group(0)),
                text,
            )
        for index, replacement in enumerate(neutral_values):
            text = text.replace(f"\ufff4{index}\ufff5", replacement)
        return text

    def reveal_obj(self, value: Any) -> Any:
        """Return a copy with embedded pseudocodes and neutral labels restored."""
        if not self.enabled:
            return value
        if isinstance(value, pd.DataFrame):
            out = value.copy()
            for column in out.columns:
                if pd.api.types.is_object_dtype(out[column]) or pd.api.types.is_string_dtype(
                    out[column]
                ):
                    out[column] = out[column].map(self.reveal_text)
            return out
        if isinstance(value, str):
            return self.reveal_text(value)
        if isinstance(value, dict):
            revealed = {
                self.reveal_text(key) if isinstance(key, str) else key: self.reveal_obj(item)
                for key, item in value.items()
            }
            code_key = "stock_code" if revealed.get("stock_code") is not None else "code"
            name_key = "stock_name" if code_key == "stock_code" else "name"
            stock_code = revealed.get(code_key)
            if stock_code is not None:
                normalized_code = str(stock_code).zfill(6)
                current_name = str(revealed.get(name_key) or "").strip()
                if normalized_code in self._names and (
                    not current_name or current_name == normalized_code
                ):
                    revealed[name_key] = self._names[normalized_code]
            return revealed
        if isinstance(value, list):
            return [self.reveal_obj(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.reveal_obj(item) for item in value)
        return value

    def mask_obj(self, value: Any) -> Any:
        """Mask codes, names, and free text in nested Agent-facing results."""
        if not self.enabled:
            return value
        if isinstance(value, pd.DataFrame):
            return self.mask_df(value)
        if isinstance(value, str):
            return self.mask_text(value)
        if isinstance(value, dict):
            return {
                self.mask_text(key) if isinstance(key, str) else key: self.mask_obj(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.mask_obj(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.mask_obj(item) for item in value)
        return value
