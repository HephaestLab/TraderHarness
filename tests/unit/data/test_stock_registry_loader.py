"""The public stock universe excludes indices and funds."""

from traderharness.data.stock_registry_loader import (
    get_stock_name,
    get_stock_registry,
    is_a_share_stock_code,
)


def test_a_share_code_filter():
    assert is_a_share_stock_code("600519")
    assert is_a_share_stock_code("301001")
    assert is_a_share_stock_code("688001")
    assert is_a_share_stock_code("920001")
    assert not is_a_share_stock_code("399262")
    assert not is_a_share_stock_code("510300")
    assert not is_a_share_stock_code("02513")
    assert not is_a_share_stock_code("0025130")


def test_public_registry_excludes_index_codes():
    registry = get_stock_registry()

    assert "600519" in registry
    assert "399262" not in registry


def test_registry_names_remove_source_null_padding():
    assert get_stock_name("002403") == "爱仕达"
