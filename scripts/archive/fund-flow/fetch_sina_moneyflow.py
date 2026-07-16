# -*- coding: utf-8 -*-
import sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
import requests

headers = {'User-Agent': 'Mozilla/5.0'}
proxies = {'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}

# 新浪行业板块资金流API
# https://money.finance.sina.com.cn/moneyflow/
urls = [
    'https://money.finance.sina.com.cn/moneyflow/moneyflow_bkzj_trade.html',
    'https://money.finance.sina.com.cn/q/go.php/vFundFlowNew/kind/industry/index.phtml',
    'https://money.finance.sina.com.cn/moneyflow/industry/',
]

for url in urls:
    try:
        r = requests.get(url, headers=headers, proxies=proxies, timeout=10)
        has_data = '净流入' in r.text or 'moneyflow' in r.text.lower() or '资金' in r.text
        print(f'{url[-50:]}: {r.status_code}, len={len(r.text)}, has_data={has_data}')
    except Exception as e:
        print(f'{url[-50:]}: FAIL')

# 新浪行业资金流JSON接口
# 这个才是真正可用的
json_urls = [
    'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_bk?page=1&num=40&sort=netamount&asc=0&fenlei=1',
    'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_bk?page=1&num=100&sort=netamount&asc=0&fenlei=1&bankuai=industry',
]

for url in json_urls:
    try:
        r = requests.get(url, headers=headers, proxies=proxies, timeout=10)
        print(f'\nJSON接口: {r.status_code}')
        if r.status_code == 200 and r.text.startswith('['):
            data = json.loads(r.text)
            print(f'  获取到 {len(data)} 条')
            if data:
                print(f'  字段: {list(data[0].keys())}')
                for item in data[:3]:
                    print(f"  {item.get('name','?')}: 净流入={item.get('netamount','?')}")
        elif r.status_code == 200:
            print(f'  preview: {r.text[:200]}')
    except Exception as e:
        print(f'  FAIL: {e}')
