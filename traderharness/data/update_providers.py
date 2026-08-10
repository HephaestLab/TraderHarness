"""Production network providers for incremental canonical-data updates."""

from __future__ import annotations

import hashlib
import json
import logging
import socket
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, as_completed, wait
from datetime import date, datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pyarrow.parquet as pq

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
        workers: int = 1,
        timeout: float = 20,
        max_attempts: int = 4,
        retry_delay: float = 1,
        request_delay: float = 0.15,
        max_passes: int = 6,
        pass_delay: float = 30,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.workers = workers
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
        self.request_delay = request_delay
        self.max_passes = max_passes
        self.pass_delay = pass_delay
        self.last_failed: list[str] = []
        self.progress_path: Path | None = None

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
            "klt": "5",
            "fqt": "0",
            "beg": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "lmt": "1000000",
            "fields1": self._FIELDS1,
            "fields2": self._FIELDS2,
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
        }
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                if self.request_delay:
                    time.sleep(self.request_delay)
                response = client.get(self._URL, params=params)
                response.raise_for_status()
                payload = response.json()
                if payload.get("rc") not in (None, 0):
                    raise RuntimeError(f"Eastmoney rc={payload.get('rc')}")
                data = payload.get("data")
                if data is None:
                    return pd.DataFrame(columns=EASTMONEY_5MIN_COLUMNS)
                frame = parse_eastmoney_5min_klines(code, data.get("klines") or [])
                if not frame.empty:
                    dates = frame["datetime"].dt.date
                    frame = frame[(dates >= start) & (dates <= end)].reset_index(drop=True)
                return frame
            except Exception as exc:  # noqa: BLE001 - retry network and malformed payloads
                last_error = exc
                if attempt < self.max_attempts:
                    time.sleep(self.retry_delay * attempt)
        raise RuntimeError(f"Eastmoney 5min failed for {code}: {last_error}") from last_error

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
            "Connection": "close",
        }
        limits = httpx.Limits(max_connections=self.workers, max_keepalive_connections=self.workers)
        pass_number = 0
        while pending and pass_number < self.max_passes:
            pass_number += 1
            failed = []
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


def _fetch_baostock_batch(args) -> tuple[pd.DataFrame, list[str]]:
    codes, start, end, frequency, socket_timeout = args
    import baostock as bs

    socket.setdefaulttimeout(socket_timeout)
    failed: list[str] = []
    frames: list[pd.DataFrame] = []
    try:
        login = bs.login()
        if login.error_code != "0":
            return pd.DataFrame(), list(codes)
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
    ) -> None:
        self.frequency = frequency
        self.workers = workers
        self.batch_size = batch_size
        self.socket_timeout = socket_timeout
        self.stall_timeout = stall_timeout
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
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
        jobs = [(batch, start, end, self.frequency, self.socket_timeout) for batch in batches]
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


class BaostockCsi300Provider:
    """Fetch the real CSI 300 index (sh.000300), unadjusted."""

    def fetch(self, start: date, end: date) -> pd.DataFrame:
        import baostock as bs

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
        finally:
            try:
                bs.logout()
            except Exception:
                pass


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

    @staticmethod
    def _page(client: httpx.Client, se_date: str, page: int) -> dict:
        data = {
            "pageNum": str(page),
            "pageSize": "30",
            "tabName": "fulltext",
            "seDate": se_date,
            "isHLtitle": "true",
        }
        for attempt in range(3):
            try:
                response = client.post(CNINFO_URL, data=data)
                response.raise_for_status()
                payload = response.json()
                total = int(payload.get("totalAnnouncement", 0))
                return {
                    "items": payload.get("announcements") or [],
                    "pages": (total + 29) // 30,
                }
            except (httpx.HTTPError, ValueError):
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
        return {"items": [], "pages": 0}


CLS_URL = "https://www.cls.cn/v1/roll/get_roll_list"
CLS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.cls.cn/telegraph",
}


def cls_sign(params: dict) -> str:
    query = "&".join(f"{key}={params[key]}" for key in sorted(params))
    return hashlib.md5(hashlib.sha1(query.encode()).hexdigest().encode()).hexdigest()


class ClsNewsProvider:
    def __init__(self, delay: float = 0.3) -> None:
        self.delay = delay

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

    @staticmethod
    def _page(client: httpx.Client, last_time: int) -> list[dict]:
        params = {
            "app": "CailianpressWeb",
            "os": "web",
            "sv": "7.7.5",
            "rn": "50",
            "last_time": str(last_time),
            "refresh_type": "1",
        }
        params["sign"] = cls_sign(params)
        for attempt in range(3):
            try:
                response = client.get(CLS_URL, params=params)
                response.raise_for_status()
                return response.json().get("data", {}).get("roll_data", [])
            except (httpx.HTTPError, ValueError):
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
        return []
