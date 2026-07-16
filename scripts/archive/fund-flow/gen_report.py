# -*- coding: utf-8 -*-
import sys, json
sys.stdout.reconfigure(encoding='utf-8')

with open('heatmap_rows.html', 'r', encoding='utf-8') as f:
    heatmap_rows = f.read()

with open('industry_heatmap_rows.html', 'r', encoding='utf-8') as f:
    industry_heatmap_rows = f.read()

html_top = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股每日复盘 - 2026年5月21日</title>
<style>
:root {
  --bg:#0f0f1a; --bg-card:#1a1a2e; --bg-alt:#16213e;
  --text:#e8e8e8; --text2:#a0a0b0;
  --red:#ff4444; --red-l:#ff6b6b; --green:#00c853; --green-l:#69f0ae;
  --gold:#ffd700; --blue:#4fc3f7; --border:#2a3a5e;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text);line-height:1.5;padding:16px;max-width:1800px;margin:0 auto}
h1{font-size:1.8rem;text-align:center;margin-bottom:4px}
h2{font-size:1.3rem;margin:28px 0 12px;color:var(--blue);border-left:4px solid var(--blue);padding-left:10px}
h3{font-size:1rem;margin:14px 0 8px;color:var(--text2)}
.header{text-align:center;padding:20px 0;border-bottom:1px solid var(--border);margin-bottom:20px}
.header .sub{font-size:0.85rem;color:var(--text2)}
.card{background:var(--bg-card);border-radius:10px;padding:16px;margin:12px 0;border:1px solid var(--border)}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.idx{background:var(--bg-alt);border-radius:8px;padding:12px;text-align:center}
.idx .n{font-size:0.8rem;color:var(--text2)}
.idx .p{font-size:1.4rem;font-weight:bold;margin:2px 0}
.idx .c{font-size:0.95rem;font-weight:bold}
.up{color:var(--red)} .dn{color:var(--green)}
.flex{display:flex;flex-wrap:wrap;gap:12px;margin:8px 0}
.si{flex:1;min-width:140px;background:var(--bg-alt);border-radius:6px;padding:10px 12px}
.si .l{font-size:0.75rem;color:var(--text2)}
.si .v{font-size:1.1rem;font-weight:bold;margin-top:2px}
.divider{height:1px;background:linear-gradient(to right,transparent,var(--border),transparent);margin:28px 0}

.hm-wrap{overflow-x:auto;max-height:75vh;overflow-y:auto}
.hm{border-collapse:separate;border-spacing:1px;width:100%;font-size:0.72rem}
.hm th{position:sticky;top:0;z-index:2;background:var(--bg);padding:6px 4px;color:var(--text2);font-size:0.7rem;text-align:center}
.hm th:first-child{text-align:left;min-width:100px;left:0;z-index:3}
.hm td{padding:4px 3px;text-align:center;border-radius:3px;font-weight:600;white-space:nowrap}
.hm td .amt{font-size:0.6rem;font-weight:400;opacity:0.7;margin-top:1px}
.hm .sector-name{text-align:left;background:var(--bg-card)!important;color:var(--text);font-weight:500;position:sticky;left:0;z-index:1;min-width:100px;font-size:0.73rem}
.h5up{background:rgba(255,68,68,0.55);color:#ffcdd2}
.h4up{background:rgba(255,68,68,0.4);color:#ffcdd2}
.h3up{background:rgba(255,68,68,0.28);color:#ef9a9a}
.h2up{background:rgba(255,100,100,0.18);color:#ef9a9a}
.h1up{background:rgba(255,150,150,0.1);color:#e0bfbf}
.h0{background:rgba(158,158,158,0.08);color:#9e9e9e}
.h1dn{background:rgba(0,200,83,0.1);color:#a5d6a7}
.h2dn{background:rgba(0,200,83,0.18);color:#a5d6a7}
.h3dn{background:rgba(0,200,83,0.28);color:#69f0ae}
.h4dn{background:rgba(0,200,83,0.4);color:#69f0ae}
.h5dn{background:rgba(0,200,83,0.55);color:#b9f6ca}
.cum-up{background:rgba(255,68,68,0.12);color:var(--red-l);font-weight:bold}
.cum-dn{background:rgba(0,200,83,0.12);color:var(--green-l);font-weight:bold}
.f-in-big{background:rgba(255,215,0,0.35);color:#fff8e1;font-weight:bold}
.f-in{background:rgba(255,215,0,0.18);color:#ffe082}
.f-flat{background:rgba(158,158,158,0.08);color:#bdbdbd}
.f-out{background:rgba(96,125,139,0.15);color:#b0bec5}
.f-out-med{background:rgba(96,125,139,0.3);color:#90a4ae}
.f-out-big{background:rgba(96,125,139,0.45);color:#78909c;font-weight:bold}

.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}
.cal-header{background:var(--bg-alt);padding:8px 4px;text-align:center;font-size:0.75rem;color:var(--blue);font-weight:600;border-radius:4px}
.cal-day{background:var(--bg-alt);border-radius:4px;padding:6px;min-height:85px;font-size:0.7rem}
.cal-day.empty{background:transparent;border:1px dashed rgba(255,255,255,0.03);min-height:20px}
.cal-day.today{border:2px solid var(--gold)}
.cal-day.weekend{opacity:0.5}
.cal-day .d{font-weight:bold;font-size:0.8rem;margin-bottom:3px;color:var(--text)}
.cal-day .ev{margin:2px 0;padding:2px 4px;border-radius:3px;font-size:0.63rem;line-height:1.3}
.ev-critical{background:rgba(255,68,68,0.25);color:#ffcdd2;border-left:2px solid var(--red)}
.ev-high{background:rgba(255,152,0,0.2);color:#ffcc80;border-left:2px solid #ff9800}
.ev-medium{background:rgba(79,195,247,0.15);color:#b3e5fc;border-left:2px solid var(--blue)}
.ev-low{background:rgba(158,158,158,0.1);color:#bdbdbd;border-left:2px solid #757575}
.ev-holiday{background:rgba(156,39,176,0.15);color:#ce93d8;border-left:2px solid #9c27b0}
.legend{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0;font-size:0.7rem}
.legend span{padding:2px 8px;border-radius:3px}

table.rank{width:100%;border-collapse:collapse;font-size:0.82rem}
table.rank th{background:var(--bg-alt);padding:8px 6px;text-align:left;color:var(--blue);border-bottom:2px solid var(--border)}
table.rank td{padding:6px;border-bottom:1px solid var(--border)}
.tag{display:inline-block;padding:1px 6px;border-radius:3px;font-size:0.7rem;margin:1px}
.tag-r{background:rgba(255,68,68,0.15);color:var(--red-l)}
.tag-g{background:rgba(0,200,83,0.15);color:var(--green-l)}
.tag-y{background:rgba(255,215,0,0.12);color:var(--gold)}
.tag-b{background:rgba(79,195,247,0.12);color:var(--blue)}
.disclaimer{margin-top:32px;padding:12px;background:rgba(255,255,255,0.02);border-radius:6px;font-size:0.7rem;color:var(--text2);text-align:center}
@media(max-width:768px){.grid4{grid-template-columns:repeat(2,1fr)}.cal-grid{grid-template-columns:repeat(4,1fr)}}
</style>
</head>
<body>

<div class="header">
  <h1>A股每日复盘</h1>
  <div class="sub">2026年5月21日 星期四 | 数据：AKShare/stock-data-mcp/Exa | 生成：2026-05-22</div>
</div>

<h2>Module 1: 每日复盘</h2>
<div class="grid4">
  <div class="idx"><div class="n">上证指数</div><div class="p dn">4077.28</div><div class="c dn">-2.04%</div></div>
  <div class="idx"><div class="n">深证成指</div><div class="p dn">15247.27</div><div class="c dn">-2.07%</div></div>
  <div class="idx"><div class="n">创业板指</div><div class="p dn">3829.78</div><div class="c dn">-2.35%</div></div>
  <div class="idx"><div class="n">科创50</div><div class="p dn">1764.17</div><div class="c dn">-3.70%</div></div>
</div>
<div class="card">
  <div class="flex">
    <div class="si"><div class="l">沪深300</div><div class="v dn">4783.10 (-1.39%)</div></div>
    <div class="si"><div class="l">成交额</div><div class="v" style="color:var(--gold)">~3.48万亿 (+16%放量)</div></div>
    <div class="si"><div class="l">涨跌比</div><div class="v dn">476:2733 = 1:5.7</div></div>
    <div class="si"><div class="l">涨停/跌停</div><div class="v">34 / 25</div></div>
  </div>
  <div class="flex">
    <div class="si"><div class="l">主力净流入</div><div class="v dn">-1451亿 (-4.17%)</div></div>
    <div class="si"><div class="l">超大单</div><div class="v dn">-851亿</div></div>
    <div class="si"><div class="l">板块涨跌</div><div class="v dn">4涨/86跌(行业)</div></div>
    <div class="si"><div class="l">最高连板</div><div class="v up">威龙股份 7板</div></div>
  </div>
  <p style="margin-top:10px;font-size:0.82rem;color:var(--text2)">
    <strong style="color:var(--red-l)">冲高诱多后砸盘：</strong>上证早盘冲4199.53后急跌至4074.22，振幅125点。科技全面崩塌(半导体-6%,通信-5.6%)，新能源暴跌(光伏/风电-4.4%)。仅银行/航运/白酒飘红。主力连续8日净流出，今日-1451亿创峰值。
  </p>
</div>

<div class="divider"></div>
<h2>Module 2A: 行业板块7日涨跌 + 资金流 (全量90个)</h2>
<p style="font-size:0.72rem;color:var(--text2);margin:4px 0 0">每格上方=日涨跌幅 | 每格下方=当日成交额(亿) | 末列=当日主力净流入(亿,来源:同花顺) | 7日逐日净流入因 push2.eastmoney.com 被网络层阻断暂无法获取,后续可通过定时任务积累</p>
<div class="card">
  <div class="legend">
    <span class="h5up">涨5%+</span><span class="h3up">涨2~3%</span><span class="h1up">涨0.3~1%</span>
    <span class="h0">平盘</span>
    <span class="h1dn">跌0.3~1%</span><span class="h3dn">跌2~3%</span><span class="h5dn">跌5%+</span>
    <span style="margin-left:12px" class="f-in-big">流入20亿+</span><span class="f-in">流入5~20亿</span>
    <span class="f-out">流出0~10亿</span><span class="f-out-med">流出10~50亿</span><span class="f-out-big">流出50亿+</span>
  </div>
  <div class="hm-wrap" style="max-height:60vh">
    <table class="hm">
      <thead><tr><th>行业</th><th>5/14</th><th>5/15</th><th>5/18</th><th>5/19</th><th>5/20</th><th>5/21</th><th>7日累计</th><th>今日资金流</th></tr></thead>
      <tbody>
""" + industry_heatmap_rows + """      </tbody>
    </table>
  </div>
</div>

<h2>Module 2B: 概念板块7日涨跌热力网格 (全量374个)</h2>
<div class="card">
  <div class="legend">
    <span class="h5up">涨5%+</span><span class="h3up">涨2~3%</span><span class="h1up">涨0.3~1%</span>
    <span class="h0">平盘</span>
    <span class="h1dn">跌0.3~1%</span><span class="h3dn">跌2~3%</span><span class="h5dn">跌5%+</span>
    <span style="color:var(--text2)">| 红涨绿跌 | 按7日累计降序</span>
  </div>
  <div class="hm-wrap">
    <table class="hm">
      <thead><tr><th>概念板块</th><th>5/14</th><th>5/15</th><th>5/18</th><th>5/19</th><th>5/20</th><th>5/21</th><th>7日累计</th></tr></thead>
      <tbody>
"""

html_mid = heatmap_rows

html_bot = """      </tbody>
    </table>
  </div>
</div>

<div class="divider"></div>
<h2>Module 3: 财经日历 (日历视图)</h2>
<div class="card">
  <div class="legend">
    <span class="ev-critical" style="padding:3px 8px">极重要(全市场)</span>
    <span class="ev-high" style="padding:3px 8px">重要(多板块)</span>
    <span class="ev-medium" style="padding:3px 8px">中等(单板块)</span>
    <span class="ev-low" style="padding:3px 8px">一般</span>
    <span class="ev-holiday" style="padding:3px 8px">休市</span>
  </div>

  <h3 style="margin-top:16px">5月22日 ~ 5月31日</h3>
  <div class="cal-grid">
    <div class="cal-header">一</div><div class="cal-header">二</div><div class="cal-header">三</div><div class="cal-header">四</div><div class="cal-header">五</div><div class="cal-header">六</div><div class="cal-header">日</div>
    <div class="cal-day empty"></div><div class="cal-day empty"></div><div class="cal-day empty"></div>
    <div class="cal-day today"><div class="d">22</div><div class="ev ev-critical">英伟达盘后财报+电话会</div><div class="ev ev-high">美联储4月会议纪要</div><div class="ev ev-medium">央行净投放1000亿维稳</div><div class="ev ev-low">税期走款日</div></div>
    <div class="cal-day"><div class="d">23</div><div class="ev ev-high">英伟达业绩A股映射(算力/光模块)</div><div class="ev ev-medium">欧洲央行执委讲话</div></div>
    <div class="cal-day weekend"><div class="d">24</div></div>
    <div class="cal-day weekend"><div class="d">25</div></div>
    <div class="cal-day"><div class="d">26</div><div class="ev ev-medium">5月制造业PMI预览值</div><div class="ev ev-low">央行逆回购操作观察</div></div>
    <div class="cal-day"><div class="d">27</div><div class="ev ev-medium">美国消费者信心指数</div><div class="ev ev-low">5月工业利润数据窗口</div></div>
    <div class="cal-day"><div class="d">28</div><div class="ev ev-high">和辉光电80.57亿股解禁(占58%)</div><div class="ev ev-medium">美国Q1 GDP修正值</div></div>
    <div class="cal-day"><div class="d">29</div><div class="ev ev-high">美国4月核心PCE物价</div><div class="ev ev-medium">美国初请失业金</div></div>
    <div class="cal-day"><div class="d">30</div><div class="ev ev-critical">中国5月官方PMI(制造业+服务业)</div><div class="ev ev-medium">月末资金面+地方债发行</div></div>
    <div class="cal-day weekend"><div class="d">31</div></div>
    <div class="cal-day weekend"><div class="d">6/1</div></div>
  </div>

  <h3 style="margin-top:16px">6月1日 ~ 6月15日</h3>
  <div class="cal-grid">
    <div class="cal-header">一</div><div class="cal-header">二</div><div class="cal-header">三</div><div class="cal-header">四</div><div class="cal-header">五</div><div class="cal-header">六</div><div class="cal-header">日</div>
    <div class="cal-day"><div class="d">2</div><div class="ev ev-high">COMPUTEX台北电脑展开幕(AI算力)</div><div class="ev ev-high">5月财新制造业PMI</div></div>
    <div class="cal-day"><div class="d">3</div><div class="ev ev-medium">COMPUTEX Day2(GPU/HBM)</div><div class="ev ev-medium">美联储褐皮书</div></div>
    <div class="cal-day"><div class="d">4</div><div class="ev ev-medium">COMPUTEX Day3</div><div class="ev ev-medium">5月财新服务业PMI</div></div>
    <div class="cal-day"><div class="d">5</div><div class="ev ev-medium">COMPUTEX闭幕</div><div class="ev ev-medium">美国ISM服务业PMI</div></div>
    <div class="cal-day"><div class="d">6</div><div class="ev ev-critical">美国5月非农就业数据</div><div class="ev ev-medium">6月沪深300/中证500调样预测</div></div>
    <div class="cal-day weekend"><div class="d">7</div></div>
    <div class="cal-day weekend"><div class="d">8</div></div>
    <div class="cal-day"><div class="d">9</div><div class="ev ev-high">苹果WWDC 2026开幕</div><div class="ev ev-high">中国5月进出口数据</div></div>
    <div class="cal-day"><div class="d">10</div><div class="ev ev-high">中国5月CPI/PPI</div><div class="ev ev-medium">WWDC Day2(AI/Vision Pro)</div></div>
    <div class="cal-day"><div class="d">11</div><div class="ev ev-critical">美国5月CPI</div><div class="ev ev-medium">美联储Z.1金融账户</div></div>
    <div class="cal-day"><div class="d">12</div><div class="ev ev-high">美国5月PPI</div><div class="ev ev-medium">科创板改革"1+6"落地观察</div></div>
    <div class="cal-day"><div class="d">13</div><div class="ev ev-medium">WWDC闭幕</div><div class="ev ev-low">美国密歇根消费者信心</div></div>
    <div class="cal-day weekend"><div class="d">14</div></div>
    <div class="cal-day weekend"><div class="d">15</div></div>
  </div>

  <h3 style="margin-top:16px">6月16日 ~ 6月30日</h3>
  <div class="cal-grid">
    <div class="cal-header">一</div><div class="cal-header">二</div><div class="cal-header">三</div><div class="cal-header">四</div><div class="cal-header">五</div><div class="cal-header">六</div><div class="cal-header">日</div>
    <div class="cal-day"><div class="d">16</div><div class="ev ev-critical">FOMC会议Day1</div><div class="ev ev-high">中国5月经济数据(工业/零售/投资)</div><div class="ev ev-high">中国5月社融/信贷</div></div>
    <div class="cal-day"><div class="d">17</div><div class="ev ev-critical">FOMC利率决议+SEP+点阵图</div><div class="ev ev-critical">鲍威尔新闻发布会</div></div>
    <div class="cal-day"><div class="d">18</div><div class="ev ev-high">节前最后交易日(消化FOMC)</div><div class="ev ev-medium">6月指数调样正式生效</div><div class="ev ev-medium">美国工业产出</div></div>
    <div class="cal-day"><div class="d" style="color:#ce93d8">19</div><div class="ev ev-holiday">端午节休市</div><div class="ev ev-holiday">美国六月节休市</div></div>
    <div class="cal-day weekend"><div class="d">20</div><div class="ev ev-holiday">端午节休市</div></div>
    <div class="cal-day weekend"><div class="d">21</div><div class="ev ev-holiday">端午节休市</div></div>
    <div class="cal-day empty"></div>
    <div class="cal-day"><div class="d">22</div><div class="ev ev-high">节后开市(消化FOMC+3天外围)</div><div class="ev ev-medium">6月LPR报价</div></div>
    <div class="cal-day"><div class="d">23</div><div class="ev ev-medium">6月IPO集中受理期</div></div>
    <div class="cal-day"><div class="d">24</div><div class="ev ev-low">美联储SCOOS报告</div></div>
    <div class="cal-day"><div class="d">25</div><div class="ev ev-medium">美国Q1 GDP终值</div></div>
    <div class="cal-day"><div class="d">26</div><div class="ev ev-high">美国5月核心PCE</div></div>
    <div class="cal-day weekend"><div class="d">27</div></div>
    <div class="cal-day weekend"><div class="d">28</div></div>
    <div class="cal-day"><div class="d">29</div><div class="ev ev-medium">半年末资金面趋紧</div></div>
    <div class="cal-day"><div class="d">30</div><div class="ev ev-high">半年末最后交易日</div><div class="ev ev-high">中报预告截止(创业板)</div><div class="ev ev-high">MWC上海开幕(通信/5G)</div><div class="ev ev-medium">6月官方PMI</div></div>
    <div class="cal-day empty"></div><div class="cal-day empty"></div><div class="cal-day empty"></div><div class="cal-day empty"></div><div class="cal-day empty"></div>
  </div>

  <h3 style="margin-top:16px">7月~8月 重点事件</h3>
  <div class="cal-grid">
    <div class="cal-header">一</div><div class="cal-header">二</div><div class="cal-header">三</div><div class="cal-header">四</div><div class="cal-header">五</div><div class="cal-header">六</div><div class="cal-header">日</div>
    <div class="cal-day"><div class="d">7/1</div><div class="ev ev-high">MWC上海Day2</div><div class="ev ev-medium">6月财新PMI</div></div>
    <div class="cal-day"><div class="d">7/4</div><div class="ev ev-low">美股独立日休市</div></div>
    <div class="cal-day"><div class="d">7/9</div><div class="ev ev-medium">FOMC 6月纪要</div></div>
    <div class="cal-day"><div class="d">7/10</div><div class="ev ev-high">美国6月CPI</div></div>
    <div class="cal-day"><div class="d">7/15</div><div class="ev ev-critical">中国Q2 GDP + 6月经济数据</div><div class="ev ev-high">中报预告密集期</div></div>
    <div class="cal-day"><div class="d">7/30</div><div class="ev ev-critical">FOMC 7月利率决议</div></div>
    <div class="cal-day"><div class="d">8月</div><div class="ev ev-high">中报正式披露(截止8/31)</div><div class="ev ev-high">杰克逊霍尔全球央行年会</div><div class="ev ev-medium">ChinaJoy 2026</div><div class="ev ev-low">全年解禁最低月~1328亿</div></div>
  </div>
</div>

<div class="divider"></div>
<h2>Module 4: 板块龙头追踪</h2>
<div class="card">
  <table class="rank">
    <tr><th>板块</th><th>龙头</th><th>今日涨跌</th><th>7日</th><th>信号</th></tr>
    <tr><td>半导体</td><td>华微电子</td><td class="up">+10.03% 涨停</td><td class="dn">-6.05%</td><td><span class="tag tag-y">逆势涨停</span></td></tr>
    <tr><td>光学光电</td><td>京东方A</td><td class="up">+10.09% 涨停</td><td>-</td><td><span class="tag tag-y">封板22亿</span></td></tr>
    <tr><td>智能驾驶</td><td>德赛西威</td><td class="up">+10.00% 涨停</td><td class="dn">-3%</td><td><span class="tag tag-y">智驾独立</span></td></tr>
    <tr><td>银行</td><td>重庆银行</td><td class="up">+3.71%</td><td class="dn">-1.36%</td><td><span class="tag tag-b">避风港</span></td></tr>
    <tr><td>电力</td><td>京能电力</td><td class="up">+9.95% 涨停</td><td class="dn">-7.25%</td><td><span class="tag tag-y">公用事业</span></td></tr>
    <tr><td>贵金属</td><td>全线下跌</td><td class="dn">-2.88%</td><td class="dn">-15.08%</td><td><span class="tag tag-g">连续暴跌</span></td></tr>
    <tr><td>通信设备</td><td>通鼎互联</td><td class="dn">-9.98% 跌停</td><td class="dn">-6.47%</td><td><span class="tag tag-g">龙头跌停</span></td></tr>
    <tr><td>光伏设备</td><td>双良节能</td><td class="up">+6.56%</td><td class="dn">-5.59%</td><td><span class="tag tag-y">逆势拉升</span></td></tr>
    <tr><td>电网设备</td><td>金利华电</td><td class="up">+19.99%</td><td class="dn">-7.74%</td><td><span class="tag tag-r">2连板妖股</span></td></tr>
    <tr><td>白酒</td><td>金种子酒</td><td class="up">+4.18%</td><td class="dn">-0.92%</td><td><span class="tag tag-b">消费防御</span></td></tr>
  </table>
</div>

<div class="disclaimer">
  <strong>免责声明：</strong>本报告仅为市场数据整理和研究参考，不构成任何投资建议。投资有风险，入市需谨慎。<br>
  数据来源：AKShare(同花顺374个概念板块) / stock-data-mcp / Exa / 美联储官网 / 国家统计局 / 财联社<br>
  生成：2026-05-22 CST
</div>
</body></html>"""

output = html_top + html_mid + html_bot
out_path = r'C:\Users\admin\.claude\a-review-reports\2026-05-21.html'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(output)

print(f'Done! File size: {len(output)//1024}KB')
print(f'Saved to: {out_path}')
