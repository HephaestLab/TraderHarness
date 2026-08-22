"""Production network providers for incremental canonical-data updates."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, as_completed, wait
from datetime import date, datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pyarrow.parquet as pq

from traderharness.data.network import (
    AdaptiveRequestGate,
    ProviderBlockedError,
    ProviderCircuitOpenError,
    RequestPolicy,
    resilient_request,
)
from traderharness.data.stock_registry_loader import is_a_share_stock_code

logger = logging.getLogger(__name__)


def baostock_code(code: str) -> str:
    code = str(code).zfill(6)
    return f"sh.{code}" if code.startswith(("6", "9")) else f"sz.{code}"


EASTMONEY_5MIN_COLUMNS = [
    "stock_code",
    "date",
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
]


def parse_eastmoney_5min_klines(code: str, klines: list[str]) -> pd.DataFrame:
    """Normalize unadjusted Eastmoney 5-minute rows to canonical units."""
    rows = [item.split(",")[:7] for item in klines if len(item.split(",")) >= 7]
    if not rows:
        return pd.DataFrame(columns=EASTMONEY_5MIN_COLUMNS)
    frame = pd.DataFrame(
        rows,
        columns=["datetime", "open", "close", "high", "low", "volume", "amount"],
    )
    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce")
    frame = frame[frame["datetime"].notna()].copy()
    frame["date"] = frame["datetime"].dt.normalize()
    frame["stock_code"] = str(code).zfill(6)
    for column in ("open", "high", "low", "close", "volume", "amount"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    # Eastmoney documents minute volume in lots; the canonical dataset uses shares.
    frame["volume"] *= 100
    return frame[EASTMONEY_5MIN_COLUMNS]


class Eastmoney5MinProvider:
    """Resumable Eastmoney 5-minute updater with per-code durable staging."""

    _URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    _FIELDS1 = "f1,f2,f3,f4,f5,f6"
    _FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"

    def __init__(
        self,
        *,
        cache_dir: str | Path,
        workers: int = 4,
        timeout: float = 20,
        max_attempts: int = 4,
        retry_delay: float = 1,
        request_delay: float | None = None,
        max_passes: int = 6,
        pass_delay: float = 30,
        interval_minutes: int = 5,
    ) -> None:
        if interval_minutes not in {1, 5}:
            raise ValueError("Eastmoney minute interval must be 1 or 5")
        self.cache_dir = Path(cache_dir)
        self.workers = workers
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
        if request_delay is None:
            max_rps = max(0.1, float(os.environ.get("TRADERHARNESS_EASTMONEY_RPS", "2.5")))
            request_delay = 1.0 / max_rps
        self.request_delay = request_delay
        self.max_passes = max_passes
        self.pass_delay = pass_delay
        self.interval_minutes = interval_minutes
        self.last_failed: list[str] = []
        self.progress_path: Path | None = None
        self.request_gate = AdaptiveRequestGate(min_interval=request_delay)
        self._request_policy = RequestPolicy(
            max_attempts=max_attempts,
            base_backoff=retry_delay,
            max_backoff=max(30.0, retry_delay * 8),
        )

    @staticmethod
    def _market(code: str) -> int:
        return 1 if str(code).zfill(6).startswith("6") else 0

    def _fetch_one(
        self,
        client: httpx.Client,
        code: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        params = {
            "secid": f"{self._market(code)}.{str(code).zfill(6)}",
            "klt": str(self.interval_minutes),
            "fqt": "0",
            "beg": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "lmt": "1000000",
            "fields1": self._FIELDS1,
            "fields2": self._FIELDS2,
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
        }
        response = resilient_request(
            client,
            "GET",
            self._URL,
            params=params,
            gate=self.request_gate,
            policy=self._request_policy,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Eastmoney 5min returned malformed JSON for {code}") from exc
        if payload.get("rc") not in (None, 0):
            raise RuntimeError(f"Eastmoney rc={payload.get('rc')} for {code}")
        data = payload.get("data")
        if data is None:
            return pd.DataFrame(columns=EASTMONEY_5MIN_COLUMNS)
        frame = parse_eastmoney_5min_klines(code, data.get("klines") or [])
        if not frame.empty:
            dates = frame["datetime"].dt.date
            frame = frame[(dates >= start) & (dates <= end)].reset_index(drop=True)
        return frame

    @staticmethod
    def _cache_file(window: Path, code: str) -> Path:
        return window / f"{str(code).zfill(6)}.parquet"

    @staticmethod
    def _valid_cache(path: Path) -> bool:
        if not path.exists():
            return False
        try:
            columns = set(pq.ParquetFile(path).schema.names)
            return set(EASTMONEY_5MIN_COLUMNS).issubset(columns)
        except Exception:
            return False

    @staticmethod
    def _write_cache(path: Path, frame: pd.DataFrame) -> None:
        temporary = path.with_suffix(".parquet.tmp")
        frame.reindex(columns=EASTMONEY_5MIN_COLUMNS).to_parquet(
            temporary,
            index=False,
            compression="zstd",
        )
        temporary.replace(path)

    def _write_progress(
        self,
        *,
        total: int,
        completed: int,
        rows: int,
        failed: list[str],
        pass_number: int,
    ) -> None:
        assert self.progress_path is not None
        payload = {
            "provider": "eastmoney",
            "total_codes": total,
            "completed_codes": completed,
            "rows_downloaded_this_run": rows,
            "failed_codes": len(failed),
            "failed_preview": failed[:20],
            "pass": pass_number,
            "request_metrics": dict(self.request_gate.stats),
            "circuit_blocked_until_monotonic": self.request_gate.blocked_until,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        temporary = self.progress_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.progress_path)

    def fetch(self, codes: list[str], start: date, end: date) -> pd.DataFrame:
        normalized_codes = [str(code).zfill(6) for code in codes]
        window = self.cache_dir / f"{start.isoformat()}_{end.isoformat()}"
        window.mkdir(parents=True, exist_ok=True)
        self.progress_path = window / "progress.json"
        cached = {
            code for code in normalized_codes if self._valid_cache(self._cache_file(window, code))
        }
        pending = [code for code in normalized_codes if code not in cached]
        completed = len(cached)
        rows_downloaded = 0
        failed: list[str] = []
        self._write_progress(
            total=len(normalized_codes),
            completed=completed,
            rows=rows_downloaded,
            failed=failed,
            pass_number=0,
        )

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        }
        limits = httpx.Limits(max_connections=self.workers, max_keepalive_connections=self.workers)
        pass_number = 0
        while pending and pass_number < self.max_passes:
            pass_number += 1
            failed = []
            blocked_error: BaseException | None = None
            with httpx.Client(timeout=self.timeout, headers=headers, limits=limits) as client:
                with ThreadPoolExecutor(max_workers=self.workers) as executor:
                    futures = {
                        executor.submit(self._fetch_one, client, code, start, end): code
                        for code in pending
                    }
                    processed_in_pass = 0
                    for future in as_completed(futures):
                        code = futures[future]
                        try:
                            frame = future.result()
                            self._write_cache(self._cache_file(window, code), frame)
                            completed += 1
                            rows_downloaded += len(frame)
                        except (ProviderBlockedError, ProviderCircuitOpenError) as exc:
                            blocked_error = exc
                            logger.error("Eastmoney request circuit opened: %s", exc)
                            failed.append(code)
                        except Exception:
                            logger.exception("Eastmoney 5min failed for %s", code)
                            failed.append(code)
                        processed_in_pass += 1
                        if processed_in_pass % 25 == 0:
                            self._write_progress(
                                total=len(normalized_codes),
                                completed=completed,
                                rows=rows_downloaded,
                                failed=failed,
                                pass_number=pass_number,
                            )
            pending = sorted(failed)
            self._write_progress(
                total=len(normalized_codes),
                completed=completed,
                rows=rows_downloaded,
                failed=pending,
                pass_number=pass_number,
            )
            if blocked_error is not None:
                self.last_failed = sorted(
                    code
                    for code in normalized_codes
                    if not self._valid_cache(self._cache_file(window, code))
                )
                self._write_progress(
                    total=len(normalized_codes),
                    completed=completed,
                    rows=rows_downloaded,
                    failed=self.last_failed,
                    pass_number=pass_number,
                )
                raise RuntimeError(
                    "Eastmoney 5min provider circuit opened; no further requests were sent. "
                    f"Resume from {window} after the cooldown. Root cause: {blocked_error}"
                ) from blocked_error
            if pending and pass_number < self.max_passes:
                time.sleep(self.pass_delay * pass_number)

        self.last_failed = pending
        self._write_progress(
            total=len(normalized_codes),
            completed=completed,
            rows=rows_downloaded,
            failed=self.last_failed,
            pass_number=pass_number,
        )
        if self.last_failed:
            preview = ", ".join(self.last_failed[:10])
            raise RuntimeError(
                f"Eastmoney 5min update failed for {len(self.last_failed)} codes ({preview}). "
                f"Completed code caches are preserved at {window}."
            )

        frames = [
            pd.read_parquet(self._cache_file(window, code))
            for code in normalized_codes
        ]
        nonempty = [frame for frame in frames if not frame.empty]
        return (
            pd.concat(nonempty, ignore_index=True)
            if nonempty
            else pd.DataFrame(columns=EASTMONEY_5MIN_COLUMNS)
        )

    def cached(self, codes: list[str], start: date, end: date) -> pd.DataFrame:
        """Load only validated per-code checkpoints for fallback composition."""
        window = self.cache_dir / f"{start.isoformat()}_{end.isoformat()}"
        frames = [
            pd.read_parquet(path)
            for code in codes
            if self._valid_cache(path := self._cache_file(window, code))
        ]
        nonempty = [frame for frame in frames if not frame.empty]
        return (
            pd.concat(nonempty, ignore_index=True)
            if nonempty
            else pd.DataFrame(columns=EASTMONEY_5MIN_COLUMNS)
        )


class Eastmoney1MinProvider(Eastmoney5MinProvider):
    """Rate-limited recent one-minute trends for a small paper watch universe."""

    _TRENDS_URL = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"

    def __init__(self, *, cache_dir: str | Path | None = None, **kwargs) -> None:
        # ``fetch_latest`` is intentionally cache-free, but the parent keeps a
        # cache path for its resumable historical API. Give live callers a
        # harmless process-temporary default so constructor hardening on the
        # historical provider cannot break the paper quote path.
        if cache_dir is None:
            cache_dir = Path(tempfile.gettempdir()) / "traderharness-eastmoney-1m"
        super().__init__(cache_dir=cache_dir, interval_minutes=1, **kwargs)

    def _fetch_one(
        self,
        client: httpx.Client,
        code: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        params = {
            "secid": f"{self._market(code)}.{str(code).zfill(6)}",
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "ndays": "5",
            "iscr": "0",
        }
        response = resilient_request(
            client,
            "GET",
            self._TRENDS_URL,
            params=params,
            gate=self.request_gate,
            policy=self._request_policy,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Eastmoney 1min returned malformed JSON for {code}") from exc
        if payload.get("rc") not in (None, 0):
            raise RuntimeError(f"Eastmoney 1min rc={payload.get('rc')} for {code}")
        trends = (payload.get("data") or {}).get("trends") or []
        return parse_eastmoney_1min_trends(code, trends, start=start, end=end)

    def fetch_latest(self, codes: list[str], target_date: date) -> pd.DataFrame:
        """Fetch a fresh intraday snapshot without using the update cache.

        Paper sessions call this at most once per configured polling interval
        for a small attention set. Requests still share the provider gate,
        Retry-After handling, and circuit breaker.
        """
        normalized = sorted({str(code).zfill(6) for code in codes if code})
        if not normalized:
            return pd.DataFrame(columns=EASTMONEY_5MIN_COLUMNS)
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        }
        frames: list[pd.DataFrame] = []
        failures: list[str] = []
        limits = httpx.Limits(
            max_connections=min(self.workers, len(normalized)),
            max_keepalive_connections=min(self.workers, len(normalized)),
        )
        with httpx.Client(timeout=self.timeout, headers=headers, limits=limits) as client:
            with ThreadPoolExecutor(max_workers=min(self.workers, len(normalized))) as executor:
                futures = {
                    executor.submit(
                        self._fetch_one,
                        client,
                        code,
                        target_date,
                        target_date,
                    ): code
                    for code in normalized
                }
                for future in as_completed(futures):
                    code = futures[future]
                    try:
                        frame = future.result()
                    except (ProviderBlockedError, ProviderCircuitOpenError):
                        raise
                    except Exception as exc:  # noqa: BLE001 - report all missing symbols together
                        logger.warning("Eastmoney 1min snapshot failed for %s: %s", code, exc)
                        failures.append(code)
                        continue
                    if not frame.empty:
                        frames.append(frame)
                    else:
                        failures.append(code)
        self.last_failed = failures
        if failures and not frames:
            raise RuntimeError(
                "Eastmoney 1min live snapshot returned no usable symbols: "
                + ", ".join(failures[:10])
            )
        return (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=EASTMONEY_5MIN_COLUMNS)
        )


class Sina1MinProvider:
    """Recent one-minute bars used only as a cooperative live fallback."""

    _URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketData.getKLineData"

    def __init__(
        self,
        *,
        workers: int = 2,
        timeout: float = 20,
        max_attempts: int = 3,
        request_delay: float | None = None,
    ) -> None:
        self.workers = workers
        self.timeout = timeout
        self.last_failed: list[str] = []
        if request_delay is None:
            max_rps = max(0.1, float(os.environ.get("TRADERHARNESS_SINA_RPS", "2")))
            request_delay = 1.0 / max_rps
        self.request_gate = AdaptiveRequestGate(min_interval=request_delay)
        self._request_policy = RequestPolicy(
            max_attempts=max_attempts,
            base_backoff=1,
            max_backoff=30,
        )

    @staticmethod
    def _symbol(code: str) -> str:
        normalized = str(code).zfill(6)
        return ("sh" if normalized.startswith("6") else "sz") + normalized

    def _fetch_one(
        self,
        client: httpx.Client,
        code: str,
        target_date: date,
    ) -> pd.DataFrame:
        response = resilient_request(
            client,
            "GET",
            self._URL,
            params={
                "symbol": self._symbol(code),
                "scale": "1",
                "ma": "no",
                # One A-share session has about 240 observations. A small
                # cushion retains the complete latest session without turning
                # the fallback into a historical bulk downloader.
                "datalen": "300",
            },
            gate=self.request_gate,
            policy=self._request_policy,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Sina 1min returned malformed JSON for {code}") from exc
        if not isinstance(payload, list):
            raise RuntimeError(f"Sina 1min returned an unexpected payload for {code}")
        return parse_sina_1min_rows(code, payload, target_date=target_date)

    def fetch_latest(self, codes: list[str], target_date: date) -> pd.DataFrame:
        normalized = sorted({str(code).zfill(6) for code in codes if code})
        if not normalized:
            return pd.DataFrame(columns=EASTMONEY_5MIN_COLUMNS)
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn/",
        }
        frames: list[pd.DataFrame] = []
        failures: list[str] = []
        limits = httpx.Limits(
            max_connections=min(self.workers, len(normalized)),
            max_keepalive_connections=min(self.workers, len(normalized)),
        )
        with httpx.Client(timeout=self.timeout, headers=headers, limits=limits) as client:
            with ThreadPoolExecutor(max_workers=min(self.workers, len(normalized))) as executor:
                futures = {
                    executor.submit(self._fetch_one, client, code, target_date): code
                    for code in normalized
                }
                for future in as_completed(futures):
                    code = futures[future]
                    try:
                        frame = future.result()
                    except (ProviderBlockedError, ProviderCircuitOpenError):
                        raise
                    except Exception as exc:  # noqa: BLE001 - fallback reports missing codes together
                        logger.warning("Sina 1min snapshot failed for %s: %s", code, exc)
                        failures.append(code)
                        continue
                    if frame.empty:
                        failures.append(code)
                    else:
                        frames.append(frame)
        self.last_failed = sorted(failures)
        if failures and not frames:
            raise RuntimeError(
                "Sina 1min live snapshot returned no usable symbols: "
                + ", ".join(self.last_failed[:10])
            )
        return (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=EASTMONEY_5MIN_COLUMNS)
        )


def parse_sina_1min_rows(
    code: str,
    rows: list[dict[str, Any]],
    *,
    target_date: date,
) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty or "day" not in frame.columns:
        return pd.DataFrame(columns=EASTMONEY_5MIN_COLUMNS)
    frame["datetime"] = pd.to_datetime(frame["day"], errors="coerce")
    frame = frame[frame["datetime"].dt.date == target_date].copy()
    if frame.empty:
        return pd.DataFrame(columns=EASTMONEY_5MIN_COLUMNS)
    frame["stock_code"] = str(code).zfill(6)
    frame["date"] = frame["datetime"].dt.normalize()
    for column in ("open", "high", "low", "close", "volume", "amount"):
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    frame = frame.dropna(subset=["datetime", "open", "high", "low", "close"])
    return frame[EASTMONEY_5MIN_COLUMNS].sort_values("datetime").reset_index(drop=True)


class CascadingLiveMinuteProvider:
    """Use one live source at a time and only send missing codes to fallback."""

    def __init__(
        self,
        primary: Any,
        fallback: Any,
        *,
        primary_cooldown: float = 300,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.primary_cooldown = primary_cooldown
        self.primary_blocked_until = 0.0
        self.last_provider = "pending"
        self.last_error: str | None = None
        self.last_failed: list[str] = []

    def fetch_latest(self, codes: list[str], target_date: date) -> pd.DataFrame:
        normalized = sorted({str(code).zfill(6) for code in codes if code})
        frames: list[pd.DataFrame] = []
        primary_codes: set[str] = set()
        now = time.monotonic()
        if now >= self.primary_blocked_until:
            try:
                primary_frame = self.primary.fetch_latest(normalized, target_date)
            except Exception as exc:  # noqa: BLE001 - fallback is the recovery boundary
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.primary_blocked_until = now + self.primary_cooldown
                logger.warning(
                    "Primary live minute provider failed; cooling down and using fallback: %s",
                    exc,
                )
            else:
                if not primary_frame.empty:
                    frames.append(primary_frame)
                    primary_codes = set(primary_frame["stock_code"].astype(str).str.zfill(6))
        missing = [code for code in normalized if code not in primary_codes]
        if missing:
            try:
                fallback_frame = self.fallback.fetch_latest(missing, target_date)
            except Exception as exc:  # noqa: BLE001 - preserve a usable partial primary snapshot
                detail = f"{type(exc).__name__}: {exc}"
                self.last_error = (
                    f"{self.last_error}; fallback={detail}"
                    if self.last_error
                    else f"fallback={detail}"
                )
                if not primary_codes:
                    raise RuntimeError(
                        "All live minute providers failed; " + self.last_error
                    ) from exc
                logger.warning(
                    "Fallback live minute provider failed for missing symbols; "
                    "retaining the primary partial snapshot: %s",
                    exc,
                )
                fallback_codes = set()
            else:
                if not fallback_frame.empty:
                    frames.append(fallback_frame)
                fallback_codes = (
                    set(fallback_frame["stock_code"].astype(str).str.zfill(6))
                    if not fallback_frame.empty
                    else set()
                )
        else:
            fallback_codes = set()
        self.last_failed = sorted(set(normalized) - primary_codes - fallback_codes)
        if primary_codes and fallback_codes:
            self.last_provider = "eastmoney_1m+sina_1m"
        elif primary_codes:
            self.last_provider = "eastmoney_1m"
        else:
            self.last_provider = "sina_1m"
        nonempty = [frame for frame in frames if not frame.empty]
        return (
            pd.concat(nonempty, ignore_index=True)
            .drop_duplicates(["stock_code", "datetime"], keep="first")
            .sort_values(["stock_code", "datetime"])
            .reset_index(drop=True)
            if nonempty
            else pd.DataFrame(columns=EASTMONEY_5MIN_COLUMNS)
        )

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "selected": self.last_provider,
            "primary_error": self.last_error,
            "primary": dict(self.primary.request_gate.stats),
            "fallback": dict(self.fallback.request_gate.stats),
            "rate_limited": (
                int(self.primary.request_gate.stats.get("rate_limited", 0))
                + int(self.fallback.request_gate.stats.get("rate_limited", 0))
            ),
        }


def parse_eastmoney_1min_trends(
    code: str,
    trends: list[str],
    *,
    start: date,
    end: date,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    previous_close: float | None = None
    previous_day: date | None = None
    for item in trends:
        values = item.split(",")
        if len(values) < 7:
            continue
        timestamp = pd.to_datetime(values[0], errors="coerce")
        if pd.isna(timestamp) or not (start <= timestamp.date() <= end):
            continue
        price = pd.to_numeric(values[1], errors="coerce")
        average = pd.to_numeric(values[2], errors="coerce")
        close = float(price if pd.notna(price) and float(price) > 0 else average)
        if close <= 0:
            continue
        if previous_day != timestamp.date():
            previous_close = None
            previous_day = timestamp.date()
        open_price = previous_close if previous_close is not None else close
        raw_high = pd.to_numeric(values[3], errors="coerce")
        raw_low = pd.to_numeric(values[4], errors="coerce")
        high = max(open_price, close, float(raw_high) if pd.notna(raw_high) else close)
        low = min(open_price, close, float(raw_low) if pd.notna(raw_low) else close)
        volume = pd.to_numeric(values[5], errors="coerce")
        amount = pd.to_numeric(values[6], errors="coerce")
        rows.append(
            {
                "stock_code": str(code).zfill(6),
                "date": timestamp.normalize(),
                "datetime": timestamp,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                # Real A-share responses encode volume in board lots; the
                # canonical minute schema uses shares, matching 5-minute data.
                "volume": float(volume) * 100 if pd.notna(volume) else 0.0,
                "amount": float(amount) if pd.notna(amount) else 0.0,
            }
        )
        previous_close = close
    return pd.DataFrame(rows, columns=EASTMONEY_5MIN_COLUMNS)


class CascadingMinuteProvider:
    """Use a resumable primary source and only backfill missing codes elsewhere."""

    def __init__(self, primary: Eastmoney5MinProvider, fallback: Any) -> None:
        self.primary = primary
        self.fallback = fallback
        self.last_provider = "primary"
        self.last_error: str | None = None

    def fetch(self, codes: list[str], start: date, end: date) -> pd.DataFrame:
        try:
            frame = self.primary.fetch(codes, start, end)
            self.last_provider = "primary"
            return frame
        except Exception as exc:  # noqa: BLE001 - fallback is the recovery boundary
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Primary minute provider failed; using BaoStock fallback: %s", exc)
        cached = self.primary.cached(codes, start, end)
        cached_codes = (
            set(cached["stock_code"].astype(str).str.zfill(6))
            if not cached.empty
            else set()
        )
        missing = [str(code).zfill(6) for code in codes if str(code).zfill(6) not in cached_codes]
        fallback = self.fallback.fetch(missing, start, end) if missing else pd.DataFrame()
        frames = [frame for frame in (cached, fallback) if not frame.empty]
        self.last_provider = "fallback" if missing else "primary_cache"
        return (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=EASTMONEY_5MIN_COLUMNS)
        )

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "selected": self.last_provider,
            "primary_error": self.last_error,
            "primary_requests": dict(self.primary.request_gate.stats),
        }


def parse_baostock_rows(code: str, rows: list[list[str]], *, frequency: str) -> pd.DataFrame:
    if frequency == "d":
        columns = ["date", "code", "open", "high", "low", "close", "volume", "amount"]
        frame = pd.DataFrame(rows, columns=columns)
        frame["date"] = pd.to_datetime(frame["date"])
    else:
        columns = ["time", "code", "open", "high", "low", "close", "volume", "amount"]
        frame = pd.DataFrame(rows, columns=columns)
        frame["datetime"] = pd.to_datetime(
            frame["time"].astype(str).str[:14],
            format="%Y%m%d%H%M%S",
            errors="coerce",
        )
        frame["date"] = frame["datetime"].dt.normalize()
    frame["stock_code"] = str(code).zfill(6)
    for column in ("open", "high", "low", "close", "volume", "amount"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    selected = [
        "stock_code",
        "date",
        *(["datetime"] if frequency != "d" else []),
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ]
    return frame[selected]


def parse_baostock_valuation_rows(
    code: str,
    rows: list[list[str]],
) -> pd.DataFrame:
    columns = ["date", "code", "turn", "peTTM", "pbMRQ", "psTTM", "isST"]
    frame = pd.DataFrame(rows, columns=columns)
    frame["stock_code"] = str(code).zfill(6)
    frame["date"] = pd.to_datetime(frame["date"])
    for column in ("turn", "peTTM", "pbMRQ", "psTTM"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["isST"] = frame["isST"].astype(str).eq("1")
    return frame.rename(
        columns={
            "peTTM": "pe_ttm",
            "pbMRQ": "pb_mrq",
            "psTTM": "ps_ttm",
            "isST": "is_st",
        }
    )[
        [
            "stock_code",
            "date",
            "turn",
            "pe_ttm",
            "pb_mrq",
            "ps_ttm",
            "is_st",
        ]
    ]


FUNDAMENTAL_COLUMNS = [
    "stock_code",
    "pub_date",
    "stat_date",
    "roe",
    "net_profit_margin",
    "gross_margin",
    "net_profit",
    "eps_ttm",
    "revenue",
    "yoy_equity",
    "yoy_asset",
    "yoy_net_profit",
    "yoy_eps",
    "yoy_pni",
]

DIVIDEND_COLUMNS = [
    "stock_code",
    "ann_date",
    "bonus_shares",
    "transfer_shares",
    "cash_dividend",
    "ex_date",
    "record_date",
    "progress",
]


def _result_records(result) -> list[dict[str, str]]:
    fields = list(getattr(result, "fields", []) or [])
    rows: list[dict[str, str]] = []
    while result.next():
        values = result.get_row_data()
        rows.append(dict(zip(fields, values, strict=False)))
    return rows


def parse_baostock_fundamentals(
    code: str,
    profit_records: list[dict[str, str]],
    growth_records: list[dict[str, str]],
) -> pd.DataFrame:
    """Merge BaoStock profit/growth records into the canonical PIT schema."""

    growth = {
        (row.get("pubDate", ""), row.get("statDate", "")): row
        for row in growth_records
    }
    records: list[dict[str, Any]] = []
    for row in profit_records:
        key = (row.get("pubDate", ""), row.get("statDate", ""))
        growth_row = growth.get(key, {})

        def number(source: dict[str, str], name: str, *, scale: float = 1.0):
            value = pd.to_numeric(source.get(name), errors="coerce")
            return float(value) * scale if pd.notna(value) else None

        records.append(
            {
                "stock_code": str(code).zfill(6),
                "pub_date": row.get("pubDate", ""),
                "stat_date": row.get("statDate", ""),
                "roe": number(row, "roeAvg"),
                "net_profit_margin": number(row, "npMargin"),
                "gross_margin": number(row, "gpMargin"),
                # The current BaoStock Python client emits these as CNY even
                # though older third-party tables describe ten-thousand CNY.
                # Real-response acceptance tests anchor the canonical unit.
                "net_profit": number(row, "netProfit"),
                "eps_ttm": number(row, "epsTTM"),
                "revenue": number(row, "MBRevenue"),
                "yoy_equity": number(growth_row, "YOYEquity"),
                "yoy_asset": number(growth_row, "YOYAsset"),
                "yoy_net_profit": number(growth_row, "YOYNI"),
                "yoy_eps": number(growth_row, "YOYEPSBasic"),
                "yoy_pni": number(growth_row, "YOYPNI"),
            }
        )
    return pd.DataFrame(records, columns=FUNDAMENTAL_COLUMNS)


def parse_baostock_dividends(code: str, records: list[dict[str, str]]) -> pd.DataFrame:
    """Normalize per-share BaoStock corporate actions to per-ten-share units."""

    rows: list[dict[str, Any]] = []
    for record in records:
        ex_date = record.get("dividOperateDate", "")
        ann_date = (
            record.get("dividPlanAnnounceDate")
            or record.get("dividPreNoticeDate")
            or record.get("dividAgmPumDate")
            or ex_date
        )
        if not ann_date and not ex_date:
            continue

        def per_ten(name: str) -> float:
            value = pd.to_numeric(record.get(name), errors="coerce")
            return float(value) * 10 if pd.notna(value) else 0.0

        rows.append(
            {
                "stock_code": str(code).zfill(6),
                "ann_date": ann_date,
                "bonus_shares": per_ten("dividStocksPs"),
                "transfer_shares": per_ten("dividReserveToStockPs"),
                "cash_dividend": per_ten("dividCashPsBeforeTax"),
                "ex_date": ex_date,
                "record_date": record.get("dividRegistDate", ""),
                "progress": record.get("dividProgress") or ("实施" if ex_date else "预案"),
            }
        )
    return pd.DataFrame(rows, columns=DIVIDEND_COLUMNS)


def _fetch_baostock_fundamentals(bs, code: str, start: date, end: date, delay: float) -> pd.DataFrame:
    profit_records: list[dict[str, str]] = []
    growth_records: list[dict[str, str]] = []
    for year in range(start.year - 1, end.year + 1):
        for quarter in range(1, 5):
            if quarter == 1:
                publish_start, publish_end = date(year, 4, 1), date(year, 5, 15)
            elif quarter == 2:
                publish_start, publish_end = date(year, 7, 1), date(year, 8, 31)
            elif quarter == 3:
                publish_start, publish_end = date(year, 10, 1), date(year, 11, 15)
            else:
                publish_start, publish_end = date(year + 1, 1, 1), date(year + 1, 5, 15)
            if publish_end < start or publish_start > end:
                continue
            if delay:
                time.sleep(delay)
            profit = bs.query_profit_data(baostock_code(code), year=year, quarter=quarter)
            if profit.error_code != "0":
                raise RuntimeError(profit.error_msg)
            profit_records.extend(_result_records(profit))
            if delay:
                time.sleep(delay)
            growth = bs.query_growth_data(baostock_code(code), year=year, quarter=quarter)
            if growth.error_code != "0":
                raise RuntimeError(growth.error_msg)
            growth_records.extend(_result_records(growth))
    frame = parse_baostock_fundamentals(code, profit_records, growth_records)
    if frame.empty:
        return frame
    visible = pd.to_datetime(frame["pub_date"], errors="coerce").dt.date
    return frame[(visible >= start) & (visible <= end)].reset_index(drop=True)


def _fetch_baostock_dividends(bs, code: str, start: date, end: date, delay: float) -> pd.DataFrame:
    records: list[dict[str, str]] = []
    for year in range(start.year - 1, end.year + 1):
        if delay:
            time.sleep(delay)
        result = bs.query_dividend_data(baostock_code(code), year=str(year), yearType="report")
        if result.error_code != "0":
            raise RuntimeError(result.error_msg)
        records.extend(_result_records(result))
    frame = parse_baostock_dividends(code, records)
    if frame.empty:
        return frame
    announced = pd.to_datetime(frame["ann_date"], errors="coerce").dt.date
    operated = pd.to_datetime(frame["ex_date"], errors="coerce").dt.date
    relevant = ((announced >= start) & (announced <= end)) | (
        (operated >= start) & (operated <= end)
    )
    return frame[relevant].reset_index(drop=True)


def _fetch_baostock_batch(args) -> tuple[pd.DataFrame, list[str]]:
    codes, start, end, frequency, socket_timeout, request_interval = args
    import baostock as bs

    socket.setdefaulttimeout(socket_timeout)
    failed: list[str] = []
    frames: list[pd.DataFrame] = []
    try:
        login = bs.login()
        if login.error_code != "0":
            return pd.DataFrame(), list(codes)
        if frequency in {"fundamentals", "dividends"}:
            for code in codes:
                try:
                    if frequency == "fundamentals":
                        frame = _fetch_baostock_fundamentals(
                            bs, code, start, end, request_interval
                        )
                    else:
                        frame = _fetch_baostock_dividends(
                            bs, code, start, end, request_interval
                        )
                    if not frame.empty:
                        frames.append(frame)
                except Exception:
                    failed.append(code)
            return (
                pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(),
                failed,
            )
        if frequency == "valuation":
            fields = "date,code,turn,peTTM,pbMRQ,psTTM,isST"
            query_frequency = "d"
        elif frequency == "d":
            fields = "date,code,open,high,low,close,volume,amount"
            query_frequency = "d"
        else:
            fields = "time,code,open,high,low,close,volume,amount"
            query_frequency = frequency
        for code in codes:
            try:
                if request_interval:
                    time.sleep(request_interval)
                result = bs.query_history_k_data_plus(
                    baostock_code(code),
                    fields,
                    start_date=start.isoformat(),
                    end_date=end.isoformat(),
                    frequency=query_frequency,
                    adjustflag="3",
                )
                if result.error_code != "0":
                    failed.append(code)
                    continue
                rows = []
                while result.next():
                    rows.append(result.get_row_data())
                if rows:
                    if frequency == "valuation":
                        frames.append(parse_baostock_valuation_rows(code, rows))
                    else:
                        frames.append(parse_baostock_rows(code, rows, frequency=frequency))
            except Exception:
                failed.append(code)
    except Exception:
        failed.extend(code for code in codes if code not in failed)
    finally:
        try:
            bs.logout()
        except Exception:
            pass
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(), failed)


def retry_failed_batches(
    codes: list[str],
    fetch_once,
    *,
    max_attempts: int,
    retry_delay: float,
) -> tuple[list, list[str]]:
    """Accumulate successful frames while resubmitting only failed codes."""
    pending = list(codes)
    frames = []
    for attempt in range(1, max_attempts + 1):
        new_frames, failed = fetch_once(pending)
        frames.extend(new_frames)
        pending = sorted(set(failed))
        if not pending:
            break
        if attempt < max_attempts:
            logger.warning(
                "Retrying %d failed BaoStock codes (attempt %d/%d)",
                len(pending),
                attempt + 1,
                max_attempts,
            )
            time.sleep(retry_delay * attempt)
    return frames, pending


class BaostockProvider:
    """Multiprocess BaoStock provider (its client has process-global socket state)."""

    def __init__(
        self,
        *,
        frequency: str,
        workers: int = 2,
        batch_size: int = 10,
        socket_timeout: int = 45,
        stall_timeout: float = 120,
        max_attempts: int = 3,
        retry_delay: float = 10,
        request_interval: float | None = None,
    ) -> None:
        self.frequency = frequency
        self.workers = workers
        self.batch_size = batch_size
        self.socket_timeout = socket_timeout
        self.stall_timeout = stall_timeout
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
        if request_interval is None:
            max_rps = max(0.1, float(os.environ.get("TRADERHARNESS_BAOSTOCK_RPS", "4")))
            request_interval = max(0.0, workers / max_rps)
        self.request_interval = request_interval
        self.last_failed: list[str] = []

    def fetch(self, codes: list[str], start: date, end: date) -> pd.DataFrame:
        def fetch_once(pending: list[str]):
            return self._fetch_once(pending, start, end)

        frames, failed = retry_failed_batches(
            codes,
            fetch_once,
            max_attempts=self.max_attempts,
            retry_delay=self.retry_delay,
        )
        if failed and self.batch_size > 1:
            logger.warning(
                "Isolating %d residual BaoStock failures into single-code batches",
                len(failed),
            )
            original_batch_size = self.batch_size
            self.batch_size = 1
            try:
                isolated_frames, failed = retry_failed_batches(
                    failed,
                    fetch_once,
                    max_attempts=self.max_attempts,
                    retry_delay=self.retry_delay,
                )
                frames.extend(isolated_frames)
            finally:
                self.batch_size = original_batch_size
        self.last_failed = failed
        if self.last_failed:
            preview = ", ".join(self.last_failed[:10])
            raise RuntimeError(
                f"BaoStock {self.frequency} update failed for "
                f"{len(self.last_failed)} codes ({preview}). No partial update was written."
            )
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _fetch_once(
        self,
        codes: list[str],
        start: date,
        end: date,
    ) -> tuple[list[pd.DataFrame], list[str]]:
        batches = [
            codes[index : index + self.batch_size]
            for index in range(0, len(codes), self.batch_size)
        ]
        frames: list[pd.DataFrame] = []
        failed: list[str] = []
        jobs = [
            (batch, start, end, self.frequency, self.socket_timeout, self.request_interval)
            for batch in batches
        ]
        executor = ProcessPoolExecutor(max_workers=self.workers)
        future_batches = {
            executor.submit(_fetch_baostock_batch, job): batch
            for job, batch in zip(jobs, batches, strict=True)
        }
        pending = set(future_batches)
        completed = 0
        stalled = False
        try:
            while pending:
                done, pending = wait(
                    pending,
                    timeout=self.stall_timeout,
                    return_when=FIRST_COMPLETED,
                )
                if not done:
                    stalled = True
                    timed_out_set = {
                        code for future in pending for code in future_batches[future]
                    }
                    timed_out = [code for code in codes if code in timed_out_set]
                    failed.extend(timed_out)
                    logger.warning(
                        "BaoStock %s stalled for %.0fs; retrying %d codes in a fresh pool",
                        self.frequency,
                        self.stall_timeout,
                        len(timed_out),
                    )
                    break
                for future in done:
                    batch = future_batches[future]
                    try:
                        frame, batch_failed = future.result()
                    except Exception:
                        logger.exception("BaoStock %s batch failed", self.frequency)
                        frame, batch_failed = pd.DataFrame(), list(batch)
                    if not frame.empty:
                        frames.append(frame)
                    failed.extend(batch_failed)
                    completed += 1
                    if completed % 50 == 0:
                        logger.info(
                            "BaoStock %s: %d/%d batches",
                            self.frequency,
                            completed,
                            len(jobs),
                        )
        finally:
            if stalled:
                processes = list(getattr(executor, "_processes", {}).values())
                executor.shutdown(wait=False, cancel_futures=True)
                for process in processes:
                    if process.is_alive():
                        process.terminate()
                for process in processes:
                    process.join(timeout=5)
            else:
                executor.shutdown()
        return frames, failed


class BaostockDailyProvider(BaostockProvider):
    def __init__(self, **kwargs) -> None:
        super().__init__(frequency="d", batch_size=20, **kwargs)


class Baostock5MinProvider(BaostockProvider):
    def __init__(self, **kwargs) -> None:
        super().__init__(frequency="5", batch_size=5, **kwargs)


class BaostockValuationProvider(BaostockProvider):
    def __init__(self, **kwargs) -> None:
        super().__init__(frequency="valuation", batch_size=20, **kwargs)


class BaostockFundamentalsProvider(BaostockProvider):
    def __init__(self, **kwargs) -> None:
        super().__init__(frequency="fundamentals", batch_size=5, **kwargs)


class BaostockDividendsProvider(BaostockProvider):
    def __init__(self, **kwargs) -> None:
        super().__init__(frequency="dividends", batch_size=10, **kwargs)


class BaostockCsi300Provider:
    """Fetch the real CSI 300 index (sh.000300), unadjusted."""

    def __init__(self, *, max_attempts: int = 3, retry_delay: float = 5.0) -> None:
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay

    def fetch(self, start: date, end: date) -> pd.DataFrame:
        import baostock as bs

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                login = bs.login()
                if login.error_code != "0":
                    raise RuntimeError(f"BaoStock login failed: {login.error_msg}")
                result = bs.query_history_k_data_plus(
                    "sh.000300",
                    "date,code,open,high,low,close,volume,amount",
                    start_date=start.isoformat(),
                    end_date=end.isoformat(),
                    frequency="d",
                    adjustflag="3",
                )
                if result.error_code != "0":
                    raise RuntimeError(f"CSI 300 fetch failed: {result.error_msg}")
                rows = []
                while result.next():
                    rows.append(result.get_row_data())
                frame = parse_baostock_rows("000300", rows, frequency="d")
                return frame.drop(columns=["stock_code"])
            except Exception as exc:  # noqa: BLE001 - socket client exposes generic errors
                last_error = exc
                if attempt < self.max_attempts:
                    time.sleep(self.retry_delay * attempt)
            finally:
                try:
                    bs.logout()
                except Exception:
                    pass
        raise RuntimeError(f"CSI 300 update failed after {self.max_attempts} attempts: {last_error}") from last_error


CNINFO_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
    "Origin": "http://www.cninfo.com.cn",
    "Referer": "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
}


def parse_cninfo_announcement(item: dict[str, Any]) -> dict:
    return {
        "stock_code": str(item.get("secCode", "")).strip(),
        "stock_name": item.get("secName", ""),
        "title": item.get("announcementTitle", ""),
        "announcement_time": datetime.fromtimestamp(item.get("announcementTime", 0) / 1000),
        "pdf_url": item.get("adjunctUrl", ""),
        "ann_type": item.get("announcementTypeName", ""),
    }


class CninfoAnnouncementsProvider:
    def __init__(self, *, request_interval: float | None = None) -> None:
        if request_interval is None:
            max_rps = max(0.1, float(os.environ.get("TRADERHARNESS_CNINFO_RPS", "1")))
            request_interval = 1.0 / max_rps
        self.request_gate = AdaptiveRequestGate(min_interval=request_interval)
        self._request_policy = RequestPolicy(max_attempts=3, base_backoff=1, max_backoff=30)

    def fetch(self, start: date, end: date) -> pd.DataFrame:
        records: list[dict] = []
        with httpx.Client(headers=CNINFO_HEADERS, timeout=30) as client:
            current = start
            completed_days = 0
            while current <= end:
                se_date = f"{current}~{current}"
                first = self._page(client, se_date, 1)
                records.extend(self._parse_items(first["items"]))
                for page in range(2, first["pages"] + 1):
                    result = self._page(client, se_date, page)
                    records.extend(self._parse_items(result["items"]))
                current += timedelta(days=1)
                completed_days += 1
                if completed_days % 10 == 0:
                    logger.info(
                        "Cninfo: %d days complete, %d announcements",
                        completed_days,
                        len(records),
                    )
        return pd.DataFrame(records)

    @staticmethod
    def _parse_items(items: list[dict[str, Any]]) -> list[dict]:
        parsed = [parse_cninfo_announcement(item) for item in items]
        return [record for record in parsed if is_a_share_stock_code(record["stock_code"])]

    def _page(self, client: httpx.Client, se_date: str, page: int) -> dict:
        data = {
            "pageNum": str(page),
            "pageSize": "30",
            "tabName": "fulltext",
            "seDate": se_date,
            "isHLtitle": "true",
        }
        response = resilient_request(
            client,
            "POST",
            CNINFO_URL,
            data=data,
            gate=self.request_gate,
            policy=self._request_policy,
        )
        payload = response.json()
        total = int(payload.get("totalAnnouncement", 0))
        return {
            "items": payload.get("announcements") or [],
            "pages": (total + 29) // 30,
        }


CLS_URL = "https://www.cls.cn/v1/roll/get_roll_list"
CLS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.cls.cn/telegraph",
}


def cls_sign(params: dict) -> str:
    query = "&".join(f"{key}={params[key]}" for key in sorted(params))
    return hashlib.md5(hashlib.sha1(query.encode()).hexdigest().encode()).hexdigest()


class ClsNewsProvider:
    def __init__(self, delay: float | None = None) -> None:
        if delay is None:
            max_rps = max(0.1, float(os.environ.get("TRADERHARNESS_CLS_RPS", "1.4")))
            delay = 1.0 / max_rps
        self.delay = delay
        self.request_gate = AdaptiveRequestGate(min_interval=delay)
        self._request_policy = RequestPolicy(max_attempts=3, base_backoff=1, max_backoff=30)

    def fetch(self, start: date, end: date) -> pd.DataFrame:
        lower = int(datetime.combine(start, datetime_time.min).timestamp())
        last_time = int(datetime.combine(end + timedelta(days=1), datetime_time.min).timestamp())
        records: list[dict] = []
        empty_pages = 0
        with httpx.Client(headers=CLS_HEADERS, timeout=20) as client:
            while last_time >= lower and empty_pages < 5:
                items = self._page(client, last_time)
                if not items:
                    empty_pages += 1
                    time.sleep(1)
                    continue
                empty_pages = 0
                for item in items:
                    ctime = int(item.get("ctime", 0))
                    if ctime < lower:
                        continue
                    records.append(
                        {
                            "id": item.get("id", ""),
                            "title": item.get("title", ""),
                            "content": item.get("content", ""),
                            "ctime": ctime,
                            "display_time": datetime.fromtimestamp(ctime),
                            "level": item.get("level", ""),
                            "tags": ",".join(
                                tag.get("name", "")
                                for tag in item.get("tags", [])
                                if isinstance(tag, dict)
                            ),
                            "stock_list": ",".join(
                                stock.get("name", "")
                                for stock in item.get("stock_list", [])
                                if isinstance(stock, dict)
                            ),
                        }
                    )
                next_time = int(items[-1].get("ctime", 0))
                if next_time <= 0 or next_time >= last_time:
                    break
                last_time = next_time
                time.sleep(self.delay)
        return pd.DataFrame(records)

    def fetch_latest(
        self,
        since: datetime,
        until: datetime | None = None,
    ) -> pd.DataFrame:
        """Fetch one latest flash page for paper-trading broadcast.

        This deliberately performs one rate-gated request instead of walking
        historical pages. The caller de-duplicates IDs across minute polls.
        """
        upper = until or datetime.now()
        with httpx.Client(headers=CLS_HEADERS, timeout=20) as client:
            items = self._page(client, int(upper.timestamp()) + 1)
        records = []
        for item in items:
            ctime = int(item.get("ctime", 0))
            displayed = datetime.fromtimestamp(ctime) if ctime else None
            if displayed is None or displayed < since or displayed > upper:
                continue
            records.append(
                {
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "ctime": ctime,
                    "display_time": displayed,
                    "level": item.get("level", ""),
                    "tags": ",".join(
                        tag.get("name", "")
                        for tag in item.get("tags", [])
                        if isinstance(tag, dict)
                    ),
                    "stock_list": ",".join(
                        stock.get("name", "")
                        for stock in item.get("stock_list", [])
                        if isinstance(stock, dict)
                    ),
                }
            )
        return pd.DataFrame(records)

    def _page(self, client: httpx.Client, last_time: int) -> list[dict]:
        params = {
            "app": "CailianpressWeb",
            "os": "web",
            "sv": "7.7.5",
            "rn": "50",
            "last_time": str(last_time),
            "refresh_type": "1",
        }
        params["sign"] = cls_sign(params)
        response = resilient_request(
            client,
            "GET",
            CLS_URL,
            params=params,
            gate=self.request_gate,
            policy=self._request_policy,
        )
        return response.json().get("data", {}).get("roll_data", [])
