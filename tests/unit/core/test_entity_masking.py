"""Entity masking must be deterministic, reversible, and board-preserving."""

import pandas as pd

from traderharness.core.entity_masking import EntityMasker
from traderharness.core.market_profile import AShareProfile

CODES = ["600000", "600519", "601318", "300001", "300750", "301001", "688001", "688981"]
NAMES = {
    "600000": "浦发银行",
    "600519": "贵州茅台",
    "601318": "中国平安",
    "300001": "特锐德",
    "300750": "宁德时代",
    "301001": "凯淳股份",
    "688001": "华兴源创",
    "688981": "中芯国际",
}


def _masker(seed=42, enabled=True):
    return EntityMasker(CODES, names=NAMES, seed=seed, enabled=enabled)


def test_mapping_is_deterministic_and_bijective():
    first = _masker(seed=7)
    second = _masker(seed=7)

    assert first.real_to_masked == second.real_to_masked
    assert set(first.real_to_masked) == set(CODES)
    assert set(first.real_to_masked.values()) == set(CODES)
    assert len(first.masked_to_real) == len(CODES)


def test_groups_with_multiple_codes_have_no_identity_mapping():
    masker = _masker()
    for real, masked in masker.real_to_masked.items():
        assert real != masked


def test_mapping_preserves_exchange_board_and_price_limit_semantics():
    masker = _masker()
    profile = AShareProfile()

    for real, masked in masker.real_to_masked.items():
        assert masker.board_key(real) == masker.board_key(masked)
        assert profile.is_wide_limit(real) == profile.is_wide_limit(masked)


def test_reverse_mapping_round_trip():
    masker = _masker()
    for real in CODES:
        assert masker.unmask_code(masker.mask_code(real)) == real


def test_unknown_codes_are_unchanged():
    masker = _masker()
    assert masker.mask_code("999999") == "999999"
    assert masker.unmask_code("999999") == "999999"


def test_masks_names_aliases_and_codes_without_cascading():
    masker = EntityMasker(
        ["600000", "600519", "601318"],
        names={"600000": "长江", "600519": "长江电力", "601318": "其他公司"},
        aliases={"600519": ["长电"]},
        seed=9,
    )
    text = "长江电力（600519，简称长电）与长江600000发布公告"

    masked = masker.mask_text(text)

    assert "长江电力" not in masked
    assert "长电" not in masked
    assert "长江" not in masked
    assert masker.mask_code("600519") in masked
    assert masker.mask_code("600000") in masked


def test_masks_dataframe_code_and_free_text_columns():
    masker = _masker()
    frame = pd.DataFrame(
        {
            "stock_code": ["600519", "300750"],
            "stock_name": ["贵州茅台", "宁德时代"],
            "title": ["贵州茅台600519年度报告", "宁德时代公告"],
            "close": [1800.0, 220.0],
        }
    )

    masked = masker.mask_df(frame)

    assert frame.iloc[0]["stock_code"] == "600519"  # input is not mutated
    assert masked["stock_code"].tolist() == [
        masker.mask_code("600519"),
        masker.mask_code("300750"),
    ]
    rendered = masked.to_string()
    for secret in ("贵州茅台", "宁德时代"):
        assert secret not in rendered
    assert masked["close"].tolist() == [1800.0, 220.0]


def test_resolves_offline_entity_templates_without_double_mapping():
    masker = _masker()

    text = masker.mask_text("{{C600519}}发布年度报告")

    assert text == f"{masker.mask_name('600519')}发布年度报告"


def test_unmasks_neutral_name_for_internal_trade_storage():
    masker = _masker()
    neutral = masker.mask_name("600519")

    result = masker.unmask_obj({"stock_code": masker.mask_code("600519"), "stock_name": neutral})

    assert result == {"stock_code": "600519", "stock_name": "贵州茅台"}


def test_sanitizes_agent_generated_alias_without_remapping_pseudo_code():
    masker = _masker()
    pseudo = masker.mask_code("600519")

    text = masker.sanitize_agent_text(f"贵州茅台（{pseudo}）值得关注")

    assert text == f"{masker.mask_name('600519')}（{pseudo}）值得关注"


def test_sanitizes_historical_announcement_alias_when_registry_name_changed():
    """Registry may say ST金顶 while the model recalls the older 四川金顶 name."""
    masker = EntityMasker(
        ["600678", "600519"],
        names={"600678": "ST金顶", "600519": "贵州茅台"},
        aliases={"600678": ["{{C600678}}"]},
        sanitize_aliases={"600678": ["四川金顶", "ST金顶"]},
        seed=42,
    )

    text = masker.sanitize_agent_text("四川金顶(600155)5连板但公告无氢能收入")

    assert "四川金顶" not in text
    assert masker.mask_name("600678") in text
    # sanitize_aliases must not change point-in-time egress masking.
    assert "四川金顶" in masker.mask_text("四川金顶公告")


def test_neutral_labels_are_idempotent_under_text_masking():
    masker = _masker()
    neutral = masker.mask_name("600519")

    assert masker.mask_text(neutral) == neutral


def test_disabled_masker_is_a_noop():
    masker = _masker(enabled=False)
    frame = pd.DataFrame({"stock_code": ["600519"], "title": ["贵州茅台公告"]})

    assert masker.mask_code("600519") == "600519"
    assert masker.unmask_code("600519") == "600519"
    assert masker.mask_text("贵州茅台600519") == "贵州茅台600519"
    assert masker.mask_df(frame) is frame
