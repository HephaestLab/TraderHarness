# -*- coding: utf-8 -*-
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import requests

headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/bkzj/hy.html'}
proxies = {'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}

# 先获取 bkzj/list.js 看API定义
try:
    r = requests.get('https://data.eastmoney.com/newstatic/js/bkzj/list.js', headers=headers, proxies=proxies, timeout=10)
    print(f'list.js: {r.status_code}, len={len(r.text)}')
    # 找push2相关的URL和参数
    import re
    push2_calls = re.findall(r'push2[^"]*\.eastmoney\.com[^"]*', r.text)
    print(f'push2 calls: {push2_calls[:3]}')

    # 找所有包含 clist 或 slist 的片段
    frags = re.findall(r'["\']([^"\']*(?:clist|slist|stock)[^"\']*)["\']', r.text)
    for f in frags[:10]:
        print(f'  frag: {f}')

    # 找 fields 定义
    fields = re.findall(r'fields["\s:=]+["\'](f[0-9,f]+)["\']', r.text)
    print(f'\nfields: {fields[:3]}')

    # 找 fs 参数
    fs_params = re.findall(r'fs["\s:=]+["\']([^"\']+)["\']', r.text)
    print(f'fs: {fs_params[:5]}')

except Exception as e:
    print(f'list.js获取失败: {e}')

# 尝试用 slist/get 接口代替 clist/get
# slist 通常用于排序列表
url = 'https://push2.eastmoney.com/api/qt/slist/get'
params = {
    'pn': '1', 'pz': '100', 'po': '1', 'np': '1',
    'fltt': '2', 'invt': '2',
    'ut': 'b2884a393a59ad64002292a3e90d46a5',
    'fs': 'm:90+t:2',
    'fid': 'f62',
    'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f124',
}
try:
    r = requests.get(url, params=params, headers=headers, proxies=proxies, timeout=10)
    print(f'\nslist接口: {r.status_code}')
    data = r.json()
    if data.get('data') and data['data'].get('diff'):
        items = data['data']['diff']
        print(f'获取到 {len(items)} 个行业!')
        for item in items[:5]:
            name = item.get('f14', '?')
            flow = item.get('f62', 0)
            print(f'  {name}: 主力净流入={flow/1e8:.1f}亿')
    else:
        print(f'返回: {str(data)[:300]}')
except Exception as e:
    print(f'slist失败: {e}')
