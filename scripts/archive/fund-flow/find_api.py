# -*- coding: utf-8 -*-
import sys, re, json
sys.stdout.reconfigure(encoding='utf-8')
import requests

headers = {'User-Agent': 'Mozilla/5.0'}
proxies = {'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}

# data.eastmoney.com/bkzj/hy.html 页面里找API
r2 = requests.get('https://data.eastmoney.com/bkzj/hy.html', headers=headers, proxies=proxies, timeout=10)
text = r2.text

# 找 reportName
report_patterns = re.findall(r'reportName["\s:=]+["' + "'" + r']([A-Z_0-9]+)["' + "'" + r']', text)
print(f'reportName found: {set(report_patterns)}')

# 找datacenter-web URL
dc_patterns = re.findall(r'datacenter-web\.eastmoney\.com[^"]*', text)
print(f'\ndatacenter-web URLs: {dc_patterns[:5]}')

# 找所有JS文件
js_files = re.findall(r'src="([^"]*\.js[^"]*)"', text)
print(f'\nJS files: {len(js_files)}')

# 找一个可能包含API定义的JS
for j in js_files:
    if 'bkzj' in j or 'fund' in j.lower() or 'flow' in j.lower() or 'main' in j.lower():
        print(f'  Relevant JS: {j}')

# 找所有内嵌的URL模式
all_urls = re.findall(r'https?://[^\s"<>]+', text)
relevant = [u for u in all_urls if 'flow' in u.lower() or 'bkzj' in u or 'sector' in u.lower()]
print(f'\nRelevant URLs: {relevant[:10]}')

# 关键：试试直接用 push2.eastmoney.com 但不同路径
# 也许 /api/qt/clist/get 被拦，但别的路径不会
test_urls = [
    'https://push2.eastmoney.com/api/qt/slist/get',
    'https://push2.eastmoney.com/api/qt/stock/get',
]
for u in test_urls:
    try:
        r = requests.get(u, headers=headers, proxies=proxies, timeout=5)
        print(f'\n{u}: {r.status_code}')
    except Exception as e:
        print(f'\n{u}: FAIL')
