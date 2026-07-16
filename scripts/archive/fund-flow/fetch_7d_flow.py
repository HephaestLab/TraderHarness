# -*- coding: utf-8 -*-
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import requests

headers = {'User-Agent': 'Mozilla/5.0'}
proxies = {'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}

# 新浪行业资金流 - 试日期参数
base_url = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_bk'

dates = ['2026-05-21', '2026-05-20', '2026-05-19', '2026-05-18', '2026-05-15', '2026-05-14', '2026-05-13']

# 先试不同参数名
test_params_list = [
    {'page': '1', 'num': '100', 'sort': 'netamount', 'asc': '0', 'fenlei': '1', 'bankuai': 'industry', 'date': '2026-05-20'},
    {'page': '1', 'num': '100', 'sort': 'netamount', 'asc': '0', 'fenlei': '1', 'bankuai': 'industry', 'tradedate': '2026-05-20'},
    {'page': '1', 'num': '100', 'sort': 'netamount', 'asc': '0', 'fenlei': '1', 'bankuai': 'industry', 'day': '2026-05-20'},
]

for params in test_params_list:
    try:
        r = requests.get(base_url, params=params, headers=headers, proxies=proxies, timeout=10)
        if r.status_code == 200 and r.text.startswith('['):
            data = json.loads(r.text)
            if data:
                # 检查是否跟当天不同（通过netamount判断）
                first_net = float(data[0].get('netamount', 0))
                print(f'params={list(params.keys())[-1]}={params[list(params.keys())[-1]]}: {len(data)}条, first_net={first_net/1e8:.1f}亿 ({data[0]["name"]})')
    except Exception as e:
        print(f'FAIL: {e}')

# 对比当天数据
params_today = {'page': '1', 'num': '100', 'sort': 'netamount', 'asc': '0', 'fenlei': '1', 'bankuai': 'industry'}
r = requests.get(base_url, params=params_today, headers=headers, proxies=proxies, timeout=10)
data_today = json.loads(r.text)
print(f'\n无日期参数(today): {len(data_today)}条, first_net={float(data_today[0]["netamount"])/1e8:.1f}亿 ({data_today[0]["name"]})')

# 如果日期参数不影响结果，说明这个接口只返回当天数据
# 那就试 MoneyFlow.ssl_bkzj_bk_history 或类似接口
alt_urls = [
    'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_bk_history',
    'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_his',
]
for url in alt_urls:
    try:
        r = requests.get(url, params={'page':'1','num':'10','bankuai':'industry','date':'2026-05-20'}, headers=headers, proxies=proxies, timeout=10)
        print(f'\n{url.split("/")[-1]}: {r.status_code}')
        print(f'  {r.text[:200]}')
    except:
        print(f'{url.split("/")[-1]}: FAIL')

# 试 单个板块的历史资金流
# MoneyFlow.ssl_bkzj_ssgs_zjlr?bankuai=xxx
try:
    url = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_ssgs_zjlr'
    r = requests.get(url, params={'page':'1','num':'10','bankuai':'BK0994','sort':'tradedate','asc':'0'}, headers=headers, proxies=proxies, timeout=10)
    print(f'\nssl_bkzj_ssgs_zjlr: {r.status_code}')
    if r.text.startswith('['):
        data = json.loads(r.text)
        if data:
            print(f'  字段: {list(data[0].keys())}')
            for item in data[:5]:
                print(f"  {item}")
    else:
        print(f'  {r.text[:200]}')
except Exception as e:
    print(f'ssgs_zjlr: {e}')
