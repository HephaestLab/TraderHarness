from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "promo" / "domestic" / "final" / "douyin"
CAPTURES = ROOT / "promo" / "domestic" / "douyin-assets"
ASSETS = ROOT / "docs" / "assets"

W, H = 1080, 1920
BG = "#080d13"
PANEL = "#111923"
PANEL_2 = "#151f2b"
LINE = "#263445"
WHITE = "#f4f7fb"
MUTED = "#9aa7b8"
GREEN = "#32dc8e"
GREEN_DARK = "#153629"
AMBER = "#f3ae54"
RED = "#ff6b73"

REGULAR_FONT = Path("C:/Windows/Fonts/msyh.ttc")
BOLD_FONT = Path("C:/Windows/Fonts/msyhbd.ttc")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = BOLD_FONT if bold and BOLD_FONT.exists() else REGULAR_FONT
    return ImageFont.truetype(str(path), size=size)


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (W, H), BG)
    return image, ImageDraw.Draw(image)


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], *, fill: str = PANEL,
            outline: str | None = LINE, radius: int = 28, width: int = 2) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def wrap_text(text: str, face: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            candidate = current + char
            if current and face.getlength(candidate) > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines


def paragraph(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, *, size: int = 42,
              color: str = WHITE, max_width: int = 900, gap: int = 16,
              bold: bool = False) -> int:
    face = font(size, bold)
    x, y = xy
    for line in wrap_text(text, face, max_width):
        draw.text((x, y), line, font=face, fill=color)
        y += size + gap
    return y


def brand(draw: ImageDraw.ImageDraw, page: int, kicker: str) -> None:
    rounded(draw, (64, 64, 134, 134), fill=GREEN, outline=None, radius=14)
    draw.text((84, 80), "TH", font=font(26, True), fill=BG)
    draw.text((156, 72), "TRADERHARNESS", font=font(30, True), fill=WHITE)
    draw.text((156, 110), kicker, font=font(24), fill=MUTED)
    draw.text((930, 76), f"{page:02d}/07", font=font(25, True), fill=MUTED)


def heading(draw: ImageDraw.ImageDraw, title: str, subtitle: str | None = None,
            *, y: int = 210, size: int = 72) -> int:
    y = paragraph(draw, (64, y), title, size=size, color=WHITE, max_width=950, gap=12, bold=True)
    if subtitle:
        y += 18
        y = paragraph(draw, (68, y), subtitle, size=32, color=MUTED, max_width=930, gap=12)
    return y


def paste_panel(base: Image.Image, source: Path, box: tuple[int, int, int, int],
                *, crop: tuple[float, float, float, float] | None = None) -> None:
    image = Image.open(source).convert("RGB")
    if crop:
        left = int(image.width * crop[0])
        top = int(image.height * crop[1])
        right = int(image.width * crop[2])
        bottom = int(image.height * crop[3])
        image = image.crop((left, top, right, bottom))
    target_w = box[2] - box[0]
    target_h = box[3] - box[1]
    fitted = ImageOps.fit(image, (target_w, target_h), Image.Resampling.LANCZOS)
    mask = Image.new("L", (target_w, target_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, target_w, target_h), radius=28, fill=255)
    base.paste(fitted, (box[0], box[1]), mask)


def save(image: Image.Image, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    image.save(OUT / name, optimize=True)


def card_01() -> None:
    image, draw = canvas()
    brand(draw, 1, "开源项目 · Agent 交易评测")
    draw.text((64, 222), "Agent 炒股，", font=font(84, True), fill=WHITE)
    draw.text((64, 330), "没有一套规范的", font=font(74, True), fill=WHITE)
    draw.text((64, 432), "回测框架？", font=font(104, True), fill=GREEN)
    paragraph(
        draw,
        (68, 565),
        "不是问一次买不买，而是把整个交易过程放进统一规则。",
        size=33,
        color=MUTED,
        max_width=920,
        gap=12,
    )
    rounded(draw, (58, 690, 1022, 1298), fill=PANEL, outline=LINE, radius=34)
    paste_panel(
        image,
        ASSETS / "trade-review.png",
        (76, 708, 1004, 1280),
        crop=(0.00, 0.00, 1.00, 0.48),
    )
    rounded(draw, (92, 728, 470, 800), fill="#0c151c", outline=GREEN, radius=34)
    draw.text((130, 748), "逐笔复盘 · 成交时 K 线", font=font(27, True), fill=GREEN)
    steps = [
        (64, "决策理由", "趋势跌破止损"),
        (382, "place_order", "sell · 20,000 股"),
        (700, "执行回执", "success: true"),
    ]
    for x, title, detail in steps:
        rounded(draw, (x, 1342, x + 286, 1574), fill=PANEL_2, outline=LINE, radius=24)
        draw.text((x + 26, 1382), title, font=font(32, True), fill=WHITE)
        paragraph(draw, (x + 26, 1455), detail, size=27, color=GREEN, max_width=232, gap=9)
    draw.text((342, 1425), "→", font=font(42, True), fill=MUTED)
    draw.text((660, 1425), "→", font=font(42, True), fill=MUTED)
    rounded(draw, (64, 1625, 1016, 1775), fill=GREEN_DARK, outline=GREEN, radius=28)
    draw.text((112, 1667), "收益曲线只是结果，完整行为链才是回测", font=font(36, True), fill=GREEN)
    draw.text((66, 1832), "TraderHarness · 交易 Agent 标准实验室", font=font(28), fill=MUTED)
    save(image, "01-cover.png")


def card_02() -> None:
    image, draw = canvas()
    brand(draw, 2, "先定义什么叫回测")
    heading(
        draw,
        "只跑出收益曲线，\n算不上回测框架",
        "真正要评的是一整条行为链。",
        y=205,
        size=70,
    )
    rounded(draw, (64, 535, 1016, 1065), fill=PANEL, outline=LINE, radius=30)
    paste_panel(
        image,
        CAPTURES / "current-result-overview.png",
        (82, 553, 998, 1047),
        crop=(0.16, 0.03, 0.995, 0.98),
    )
    questions = [
        ("01", "当时看到了什么数据？"),
        ("02", "订单按什么规则成交？"),
        ("03", "为什么下单，能复现吗？"),
    ]
    y = 1110
    for num, text in questions:
        rounded(draw, (64, y, 1016, y + 150), fill=PANEL_2, outline=LINE, radius=24)
        draw.text((96, y + 48), num, font=font(30, True), fill=GREEN)
        draw.text((188, y + 40), text, font=font(39, True), fill=WHITE)
        y += 176
    rounded(draw, (64, 1660, 1016, 1792), fill=GREEN_DARK, outline=GREEN, radius=26)
    draw.text((128, 1698), "把数据、时钟、撮合、证据统一起来", font=font(37, True), fill=GREEN)
    save(image, "02-problem.png")


def card_03() -> None:
    image, draw = canvas()
    brand(draw, 3, "市场时钟 · 三阶段循环")
    heading(
        draw,
        "每天不是只问一次：\n买不买？",
        "环境把交易日拆成三段，信息逐步揭示。",
        y=205,
        size=70,
    )
    rounded(draw, (64, 520, 535, 920), fill=PANEL, outline=LINE, radius=28)
    paste_panel(
        image,
        CAPTURES / "current-live-phases.png",
        (82, 538, 517, 902),
        crop=(0.21, 0.05, 0.69, 0.56),
    )
    rounded(draw, (64, 944, 535, 1080), fill=PANEL_2, outline=LINE, radius=24)
    draw.text((96, 976), "第 1 / 1 个交易日", font=font(30, True), fill=WHITE)
    draw.text((96, 1024), "阶段事件按序进入日志", font=font(26), fill=GREEN)
    rounded(draw, (560, 520, 1016, 1080), fill=PANEL, outline=LINE, radius=28)
    paste_panel(
        image,
        CAPTURES / "current-live-phases.png",
        (578, 538, 998, 1062),
        crop=(0.69, 0.38, 0.98, 0.96),
    )
    phases = [
        ("盘前研究", "订单禁用", GREEN),
        ("开盘窗口", "09:30–10:00", AMBER),
        ("尾盘窗口", "14:30–15:00", RED),
    ]
    x_positions = [64, 382, 700]
    for x, (title, detail, color) in zip(x_positions, phases):
        rounded(draw, (x, 1130, x + 286, 1366), fill=PANEL_2, outline=LINE, radius=24)
        draw.ellipse((x + 28, 1164, x + 52, 1188), fill=color)
        draw.text((x + 28, 1210), title, font=font(34, True), fill=WHITE)
        draw.text((x + 28, 1280), detail, font=font(25), fill=MUTED)
    rounded(draw, (64, 1418, 1016, 1568), fill="#0f1820", outline=LINE, radius=24)
    draw.text((98, 1452), "显式推进", font=font(30, True), fill=GREEN)
    draw.text((300, 1452), "每个阶段完成后，环境才进入下一阶段", font=font(29), fill=WHITE)
    rounded(draw, (64, 1592, 1016, 1742), fill="#0f1820", outline=GREEN, radius=24)
    draw.text((98, 1626), "逐步揭示", font=font(30, True), fill=GREEN)
    draw.text((300, 1626), "Agent 只能读取当前窗口已经可见的数据", font=font(29), fill=WHITE)
    save(image, "03-market-clock.png")


def card_04() -> None:
    image, draw = canvas()
    brand(draw, 4, "EventBus · WebSocket 日志")
    heading(
        draw,
        "Agent 每一步，\n都要变成事件",
        "研究、工具、下单、阶段切换，不再是黑盒。",
        y=205,
        size=72,
    )
    rounded(draw, (64, 515, 1016, 805), fill=PANEL, outline=LINE, radius=28)
    paste_panel(
        image,
        CAPTURES / "current-live-events.png",
        (82, 533, 998, 787),
        crop=(0.20, 0.06, 0.98, 0.48),
    )
    rounded(draw, (64, 842, 535, 1265), fill=PANEL, outline=LINE, radius=28)
    paste_panel(
        image,
        CAPTURES / "current-live-place-orders.png",
        (82, 860, 517, 1247),
        crop=(0.695, 0.35, 0.98, 0.96),
    )
    rounded(draw, (560, 842, 1016, 1265), fill=PANEL_2, outline=LINE, radius=28)
    flow = [
        ("EventBus", "统一发出 phase / tool / order"),
        ("WS Journal", "连续序号写入可重连日志"),
        ("Live UI", "实时推送并按序去重"),
    ]
    y = 878
    for idx, (title, detail) in enumerate(flow):
        draw.text((594, y), title, font=font(31, True), fill=GREEN)
        draw.text((594, y + 48), detail, font=font(25), fill=MUTED)
        if idx < len(flow) - 1:
            draw.text((778, y + 80), "↓", font=font(30, True), fill=WHITE)
        y += 124
    labels = ["连续序号", "断线重连", "按序去重"]
    for x, label in zip((64, 382, 700), labels):
        rounded(draw, (x, 1318, x + 286, 1496), fill=PANEL_2, outline=LINE, radius=22)
        draw.text((x + 28, 1360), label, font=font(34, True), fill=WHITE)
        draw.ellipse((x + 28, 1425, x + 50, 1447), fill=GREEN)
    rounded(draw, (64, 1540, 1016, 1745), fill="#0f1820", outline=GREEN, radius=26)
    paragraph(
        draw,
        (100, 1582),
        "reasoning、工具调用、订单和阶段切换，\n都能在同一条时间线上复盘。",
        size=34,
        color=WHITE,
        max_width=860,
        gap=12,
    )
    save(image, "04-event-bus.png")


def card_05() -> None:
    image, draw = canvas()
    brand(draw, 5, "唯一订单路径 · 环境持有状态")
    heading(
        draw,
        "研究可以自由，\n下单只有一条路",
        "Agent 看只读账户；成交和持仓由环境负责。",
        y=205,
        size=72,
    )
    rounded(draw, (64, 520, 1016, 1230), fill=PANEL, outline=LINE, radius=30)
    paste_panel(
        image,
        CAPTURES / "current-result-order-full.png",
        (82, 538, 998, 1212),
        crop=(0.38, 0.04, 0.995, 0.995),
    )
    pipeline = [
        (64, "只读组合", "Agent 查询"),
        (382, "place_order", "唯一入口"),
        (700, "撮合 / 持仓", "环境更新"),
    ]
    for x, title, detail in pipeline:
        rounded(draw, (x, 1278, x + 286, 1488), fill=PANEL_2, outline=LINE, radius=24)
        draw.text((x + 26, 1318), title, font=font(32, True), fill=WHITE)
        draw.text((x + 26, 1392), detail, font=font(26), fill=GREEN)
    draw.text((342, 1352), "→", font=font(42, True), fill=MUTED)
    draw.text((660, 1352), "→", font=font(42, True), fill=MUTED)
    rounded(draw, (64, 1535, 1016, 1775), fill="#0f1820", outline=GREEN, radius=28)
    paragraph(
        draw,
        (100, 1574),
        "T+1、价格窗口、条件单、手续费和持仓约束，\n全部由环境统一执行；历史成交使用未复权价格。",
        size=32,
        color=WHITE,
        max_width=860,
        gap=12,
    )
    save(image, "05-execution-path.png")


def card_06() -> None:
    image, draw = canvas()
    brand(draw, 6, "信息边界 · 可复现实验")
    heading(
        draw,
        "遮罩只是框架里的\n一层防污染",
        "它解决实验控制，但不是整套框架的主角。",
        y=205,
        size=70,
    )
    rounded(draw, (64, 535, 1016, 1055), fill=PANEL, outline=LINE, radius=30)
    paste_panel(
        image,
        CAPTURES / "current-masking-ab.png",
        (82, 553, 998, 1037),
        crop=(0.16, 0.04, 0.995, 0.92),
    )
    details = [
        ("相对日期 + 实体伪码", "控制模型能识别出的历史身份。"),
        ("全数据出口时点安全", "日线、分钟线、新闻、公告、财务统一过滤。"),
        ("指纹回放 + 工件审计", "同样可见数据和动作，得到同样环境结果。"),
    ]
    y = 1105
    for title, body in details:
        rounded(draw, (64, y, 1016, y + 190), fill=PANEL_2, outline=LINE, radius=24)
        draw.ellipse((94, y + 38, 120, y + 64), fill=GREEN)
        draw.text((150, y + 26), title, font=font(36, True), fill=WHITE)
        draw.text((150, y + 102), body, font=font(27), fill=MUTED)
        y += 215
    save(image, "06-pit-safety.png")


def card_07() -> None:
    image, draw = canvas()
    brand(draw, 7, "开源研究基础设施")
    heading(
        draw,
        "这才是交易 Agent 的\n标准实验室",
        "把市场、工具、账户和证据放进同一套规则。",
        y=205,
        size=68,
    )
    rounded(draw, (64, 555, 1016, 1125), fill=PANEL, outline=LINE, radius=30)
    paste_panel(image, ASSETS / "office-live.png", (82, 573, 998, 1107))
    bullets = [
        "三阶段市场时钟",
        "EventBus + 可重连事件日志",
        "唯一撮合入口 + 环境持仓",
        "逐笔决策轨迹 + 回放审计",
    ]
    y = 1178
    for item in bullets:
        rounded(draw, (64, y, 1016, y + 104), fill=PANEL_2, outline=LINE, radius=22)
        draw.ellipse((96, y + 39, 122, y + 65), fill=GREEN)
        draw.text((152, y + 27), item, font=font(35, True), fill=WHITE)
        y += 120
    rounded(draw, (64, 1690, 1016, 1815), fill=GREEN_DARK, outline=GREEN, radius=62)
    draw.text((214, 1725), "GitHub 搜 TraderHarness", font=font(43, True), fill=GREEN)
    save(image, "07-cta.png")


def main() -> None:
    required = [
        CAPTURES / "current-result-overview.png",
        CAPTURES / "current-result-order-full.png",
        CAPTURES / "current-live-events.png",
        CAPTURES / "current-live-phases.png",
        CAPTURES / "current-live-place-orders.png",
        CAPTURES / "current-masking-ab.png",
        ASSETS / "office-live.png",
        ASSETS / "trade-review.png",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing source assets:\n" + "\n".join(missing))

    card_01()
    card_02()
    card_03()
    card_04()
    card_05()
    card_06()
    card_07()
    print(f"Wrote 7 Douyin cards to {OUT}")


if __name__ == "__main__":
    main()
