"""主营业务构成查询工具 — get_business_segments，按 pub_date 历史对齐。"""

from __future__ import annotations

from traderharness.tools.registry import ToolDefinition, ToolContext


async def handle_get_business_segments(params: dict, ctx: ToolContext) -> dict:
    code = params.get("stock_code", "")
    if not code:
        return {"error": "stock_code 不能为空"}

    segments_data = ctx.tool_call_cache.get("_business_segments_data")
    if segments_data is None:
        return {"error": "主营业务数据未加载"}

    stock_data = segments_data[segments_data["stock_code"] == code]
    if stock_data.empty:
        return {"error": f"{code} 无主营业务数据"}

    # Filter by pub_date <= current_date
    visible = stock_data[stock_data["pub_date"] <= str(ctx.current_date)]
    if visible.empty:
        return {"error": f"{code} 在当前交易日之前无已披露的主营构成"}

    # Get the latest report period
    latest_report = visible["report_date"].max()
    latest = visible[visible["report_date"] == latest_report]

    # Group by segment_type
    result = {
        "stock_code": code,
        "segments": [],
    }

    for _, row in latest.iterrows():
        seg = {
            "type": row.get("segment_type", ""),
            "name": row.get("segment_name", ""),
            "revenue_pct": _fmt_pct(row.get("revenue_pct")),
            "gross_margin": _fmt_pct(row.get("gross_margin")),
        }
        revenue = row.get("revenue")
        if revenue is not None and revenue == revenue:  # not NaN
            seg["revenue_billion"] = round(float(revenue) / 1e8, 2)
        result["segments"].append(seg)

    return result


def _fmt_pct(val) -> str | None:
    if val is None or val != val:  # NaN check
        return None
    return f"{float(val)*100:.1f}%"


GET_BUSINESS_SEGMENTS = ToolDefinition(
    name="get_business_segments",
    description="查询股票主营业务构成（按产品/行业/地区分类的营收占比和毛利率）。数据按财报发布日期对齐，只返回当前已公开的最新报告。",
    parameters={
        "type": "object",
        "properties": {
            "stock_code": {"type": "string", "description": "股票代码，如 600519"},
        },
        "required": ["stock_code"],
    },
    handler=handle_get_business_segments,
)
