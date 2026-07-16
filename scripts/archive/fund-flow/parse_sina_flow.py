# -*- coding: utf-8 -*-
import sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
import requests
from html.parser import HTMLParser

headers = {'User-Agent': 'Mozilla/5.0'}
proxies = {'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}

# 新浪行业资金流历史数据
# 先试试API接口
url = 'https://vip.stock.finance.sina.com.cn/q/go.php/vInvestConsult/kind/lszjlx/index.phtml'
params = {'type': 'query', 'cate': 'industry', 'date': '2026-05-21'}
r = requests.get(url, params=params, headers=headers, proxies=proxies, timeout=15)
print(f'新浪历史资金流: {r.status_code}, len={len(r.text)}')

# 提取表格数据
# 用正则提取
tables = re.findall(r'<table[^>]*>(.*?)</table>', r.text, re.DOTALL)
print(f'找到 {len(tables)} 个表格')

if tables:
    # 找最大的表格（通常是数据表）
    biggest = max(tables, key=len)
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', biggest, re.DOTALL)
    print(f'最大表格有 {len(rows)} 行')

    # 提取所有行的文本
    for row in rows[:5]:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        # 清理HTML标签
        clean_cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if clean_cells:
            print(f'  {clean_cells}')

# 试试直接获取多天的数据
print('\n--- 尝试获取多天数据 ---')
for date in ['2026-05-21', '2026-05-20', '2026-05-19']:
    params = {'type': 'query', 'cate': 'industry', 'date': date}
    r = requests.get(url, params=params, headers=headers, proxies=proxies, timeout=10)
    # 快速看有没有数据
    if '半导体' in r.text or '银行' in r.text:
        print(f'  {date}: 有数据 (len={len(r.text)})')
    else:
        print(f'  {date}: 可能无数据 (len={len(r.text)})')
