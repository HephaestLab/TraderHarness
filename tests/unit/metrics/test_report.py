"""Tests for HTML report generation."""

from datetime import date
from decimal import Decimal

from traderharness import __version__
from traderharness.metrics.performance import PerformanceMetrics
from traderharness.metrics.report import generate_html_report, save_html_report


class TestHTMLReport:
    def test_generate(self):
        metrics = PerformanceMetrics(
            total_return_pct=10.5, annual_return_pct=25.3,
            sharpe_ratio=1.5, sortino_ratio=2.1, calmar_ratio=3.0,
            max_drawdown_pct=8.2, max_consecutive_loss_days=3,
            win_rate=65.0, profit_loss_ratio=2.1, turnover_rate=1.5,
            total_trades=20, trading_days=100, final_value=1105000.0,
        )
        equity = [
            (date(2024, 1, 2), Decimal("1000000")),
            (date(2024, 4, 2), Decimal("1105000")),
        ]
        html = generate_html_report("TestAgent", metrics, equity, date(2024, 1, 2), date(2024, 4, 2))
        assert "TestAgent" in html
        assert "10.5%" in html
        assert "TraderHarness" in html
        assert f"v{__version__}" in html
        if __version__ != "0.1.0":
            assert "v0.1.0" not in html

    def test_save(self, tmp_path):
        html = "<html><body>test</body></html>"
        path = save_html_report(html, tmp_path / "report.html")
        assert path.exists()
        assert path.read_text() == html
