# -*- coding: utf-8 -*-
import sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
import requests

headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/bkzj/hy.html'}
proxies = {'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}

# 从list.js找datacenter报表名
r = requests.get('https://data.eastmoney.com/newstatic/js/bkzj/list.js', headers=headers, proxies=proxies, timeout=10)
text = r.text

# 找reportName
rn_matches = re.findall(r'reportName["\s:]+["\'](RPT_[A-Z_0-9]+)["\']', text)
print(f'reportName in list.js: {set(rn_matches)}')

# 找 datacenter-web 的完整URL调用
dc_calls = re.findall(r'datacenter[^(]*\(\)[^+]*\+[^"]*["\'](/api/[^"\']+)["\']', text)
print(f'datacenter API paths: {dc_calls[:5]}')

# 更宽松地找 RPT_ 开头的字符串
rpt_all = re.findall(r'(RPT_[A-Z_0-9]+)', text)
print(f'\n所有RPT_开头: {set(rpt_all)}')

# 找 /api/ 路径
api_paths = re.findall(r'["\'](/api/[^"\']+)["\']', text)
print(f'\nAPI paths: {set(api_paths)}')
