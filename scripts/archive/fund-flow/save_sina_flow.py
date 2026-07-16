# -*- coding: utf-8 -*-
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import requests

headers = {'User-Agent': 'Mozilla/5.0'}
proxies = {'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}

base_url = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_bk'

# fenlei=0 行业, fenlei=1 概念
all_data = {}
for fenlei, label in [(0, '行业'), (1, '概念')]:
    params = {'page': '1', 'num': '200', 'sort': 'netamount', 'asc': '0', 'fenlei': str(fenlei)}
    r = requests.get(base_url, params=params, headers=headers, proxies=proxies, timeout=15)
    if r.status_code == 200 and r.text.startswith('['):
        data = json.loads(r.text)
        all_data[label] = data
        print(f'{label}板块: {len(data)} 个')
        # 展示前5
        for item in data[:5]:
            net = float(item.get('netamount', 0)) / 1e8
            name = item.get('name', '?')
            ratio = item.get('ratioamount', '?')
            print(f'  {name}: 净流入={net:+.1f}亿 ({ratio}%)')
        print(f'  ...')
        # 后5
        for item in data[-5:]:
            net = float(item.get('netamount', 0)) / 1e8
            name = item.get('name', '?')
            print(f'  {name}: 净流入={net:+.1f}亿')
    else:
        print(f'{label}: 获取失败')

# 保存
with open('sina_fund_flow.json', 'w', encoding='utf-8') as f:
    json.dump(all_data, f, ensure_ascii=False, indent=2)
print(f'\n已保存到 sina_fund_flow.json')
