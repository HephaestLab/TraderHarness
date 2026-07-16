# -*- coding: utf-8 -*-
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import requests

headers = {'User-Agent': 'Mozilla/5.0'}
proxies = {'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}

# 方案1: 新浪行业资金流
# vip.stock.finance.sina.com.cn/q/go.php/vInvestConsult/kind/lszjlx/index.phtml
urls_to_try = [
    'https://vip.stock.finance.sina.com.cn/q/go.php/vInvestConsult/kind/lszjlx/index.phtml?type=query&cate=industry',
    'https://vip.stock.finance.sina.com.cn/moneyflow/industry/',
]

for url in urls_to_try:
    try:
        r = requests.get(url, headers=headers, proxies=proxies, timeout=10)
        print(f'{url[:60]}: {r.status_code}, len={len(r.text)}')
        if r.status_code == 200 and len(r.text) > 1000:
            # 看内容
            print(f'  preview: {r.text[:200]}')
            print()
    except Exception as e:
        print(f'{url[:60]}: FAIL - {str(e)[:60]}')

# 方案2: 腾讯行业资金流
try:
    # 腾讯板块资金流
    url = 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/mktHs/hangyeRank'
    r = requests.get(url, headers=headers, proxies=proxies, timeout=10)
    print(f'腾讯行业rank: {r.status_code}')
    if r.status_code == 200:
        print(r.text[:300])
except Exception as e:
    print(f'腾讯失败: {e}')

# 方案3: 同花顺移动端接口（可能有历史资金流）
try:
    url = 'https://dq.10jqka.com.cn/fflow/ggzjl/board/latest/2/all/desc'
    r = requests.get(url, headers=headers, proxies=proxies, timeout=10)
    print(f'\n同花顺dq接口: {r.status_code}')
    if r.status_code == 200:
        print(r.text[:500])
except Exception as e:
    print(f'同花顺dq失败: {e}')

# 方案4: 雪球行业资金流
try:
    url = 'https://stock.xueqiu.com/v5/stock/screener/fund_flow.json?type=hy&order=amount&order_type=desc'
    r = requests.get(url, headers={**headers, 'Cookie': 'xq_a_token=test'}, proxies=proxies, timeout=10)
    print(f'\n雪球: {r.status_code}')
    if r.status_code == 200:
        print(r.text[:300])
except Exception as e:
    print(f'雪球失败: {e}')
