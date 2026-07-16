"""TDD tests for DividendManager — corporate actions processing."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from traderharness.data.dividend_manager import DividendManager
from traderharness.core.portfolio import Portfolio


@pytest.fixture
def sample_dividends(tmp_path: Path) -> Path:
    df = pd.DataFrame({
        "stock_code": ["000001", "000001", "600519", "300750"],
        "ann_date": ["2024-03-01", "2024-06-01", "2024-05-01", "2024-05-01"],
        "bonus_shares": [0.0, 2.0, 0.0, 5.0],
        "transfer_shares": [0.0, 3.0, 0.0, 0.0],
        "cash_dividend": [2.28, 1.5, 27.99, 0.0],
        "ex_date": ["2024-03-15", "2024-06-15", "2024-05-20", "2024-05-20"],
        "record_date": ["2024-03-14", "2024-06-14", "2024-05-19", "2024-05-19"],
        "progress": ["实施", "实施", "实施", "实施"],
    })
    path = tmp_path / "dividends.parquet"
    df.to_parquet(path, index=False)
    return tmp_path


class TestDividendManagerLoad:
    def test_loads_data(self, sample_dividends):
        mgr = DividendManager(dataset_dir=sample_dividends)
        mgr.load()
        assert mgr._dividends is not None
        assert len(mgr._dividends) == 4

    def test_missing_file_no_crash(self, tmp_path):
        mgr = DividendManager(dataset_dir=tmp_path)
        mgr.load()
        assert mgr._dividends.empty


class TestCashDividend:
    def test_cash_dividend_adds_to_portfolio(self, sample_dividends):
        mgr = DividendManager(dataset_dir=sample_dividends)
        mgr.load()

        portfolio = Portfolio(Decimal("500000"))
        portfolio.buy("000001", "平安银行", Decimal("15.00"), 1000, date(2024, 3, 10))
        cash_before = portfolio.cash

        actions = mgr.process_day(date(2024, 3, 15), portfolio)

        assert len(actions) == 1
        assert actions[0]["stock_code"] == "000001"
        # cash_dividend = 2.28 per 10 shares, holding 1000 shares
        expected_dividend = Decimal("228.00")  # 2.28/10 * 1000
        assert portfolio.cash == cash_before + expected_dividend

    def test_no_action_if_not_holding(self, sample_dividends):
        mgr = DividendManager(dataset_dir=sample_dividends)
        mgr.load()

        portfolio = Portfolio(Decimal("500000"))
        # Not holding 000001
        actions = mgr.process_day(date(2024, 3, 15), portfolio)
        assert len(actions) == 0


class TestBonusShares:
    def test_bonus_and_transfer_increase_quantity(self, sample_dividends):
        mgr = DividendManager(dataset_dir=sample_dividends)
        mgr.load()

        portfolio = Portfolio(Decimal("500000"))
        portfolio.buy("000001", "平安银行", Decimal("15.00"), 1000, date(2024, 6, 1))

        actions = mgr.process_day(date(2024, 6, 15), portfolio)

        assert len(actions) == 1
        # bonus=2, transfer=3 per 10 shares → ratio = 0.5
        # new shares = 1000 * 0.5 = 500
        pos = portfolio.positions["000001"]
        assert pos.quantity == 1500

    def test_avg_cost_adjusted_after_bonus(self, sample_dividends):
        mgr = DividendManager(dataset_dir=sample_dividends)
        mgr.load()

        portfolio = Portfolio(Decimal("500000"))
        portfolio.buy("000001", "平安银行", Decimal("15.00"), 1000, date(2024, 6, 1))
        original_cost_basis = Decimal("15.00") * 1000  # 15000

        mgr.process_day(date(2024, 6, 15), portfolio)

        pos = portfolio.positions["000001"]
        # avg_cost should be adjusted: 15000 / 1500 = 10.00
        assert pos.avg_cost == Decimal("10.00")

    def test_pure_bonus_no_cash(self, sample_dividends):
        mgr = DividendManager(dataset_dir=sample_dividends)
        mgr.load()

        portfolio = Portfolio(Decimal("500000"))
        portfolio.buy("300750", "宁德时代", Decimal("200.00"), 500, date(2024, 5, 1))
        cash_before = portfolio.cash

        actions = mgr.process_day(date(2024, 5, 20), portfolio)

        # 300750: bonus=5, transfer=0, cash=0
        pos = portfolio.positions["300750"]
        assert pos.quantity == 750  # 500 * (1 + 5/10) = 750
        assert portfolio.cash == cash_before  # no cash dividend


class TestMultipleActionsOneDay:
    def test_multiple_stocks_same_ex_date(self, sample_dividends):
        mgr = DividendManager(dataset_dir=sample_dividends)
        mgr.load()

        portfolio = Portfolio(Decimal("1000000"))
        portfolio.buy("600519", "贵州茅台", Decimal("1800.00"), 100, date(2024, 5, 1))
        portfolio.buy("300750", "宁德时代", Decimal("200.00"), 500, date(2024, 5, 1))

        actions = mgr.process_day(date(2024, 5, 20), portfolio)

        assert len(actions) == 2
        codes = {a["stock_code"] for a in actions}
        assert codes == {"600519", "300750"}


class TestNonExDate:
    def test_no_actions_on_regular_day(self, sample_dividends):
        mgr = DividendManager(dataset_dir=sample_dividends)
        mgr.load()

        portfolio = Portfolio(Decimal("500000"))
        portfolio.buy("000001", "平安银行", Decimal("15.00"), 1000, date(2024, 3, 10))

        actions = mgr.process_day(date(2024, 3, 14), portfolio)
        assert len(actions) == 0
