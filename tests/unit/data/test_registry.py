"""Tests for StockRegistry."""

from traderharness.data.registry import StockInfo, StockRegistry


class TestStockRegistry:
    def test_register_and_get(self):
        reg = StockRegistry()
        reg.register(StockInfo(code="600519", name="贵州茅台", market="sh"))
        info = reg.get("600519")
        assert info is not None
        assert info.name == "贵州茅台"

    def test_contains(self):
        reg = StockRegistry()
        reg.register(StockInfo(code="600519", name="贵州茅台"))
        assert "600519" in reg
        assert "000001" not in reg

    def test_load_from_list(self):
        reg = StockRegistry()
        reg.load_from_list([
            {"code": "600519", "name": "贵州茅台", "market": "sh"},
            {"code": "000001", "name": "平安银行", "market": "sz"},
        ])
        assert len(reg) == 2
        assert reg.get("000001").name == "平安银行"

    def test_all_and_codes(self):
        reg = StockRegistry()
        reg.load_from_list([{"code": "600519", "name": "A"}, {"code": "000001", "name": "B"}])
        assert len(reg.all()) == 2
        assert set(reg.codes()) == {"600519", "000001"}
