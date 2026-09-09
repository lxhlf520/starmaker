#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Description: Diagnose 401: print error body, test direct-connection vs system proxy
"""
import importlib.util
import json
import os
from importlib.machinery import SourcelessFileLoader
from typing import Any, Dict, Optional

import requests

# Load tools.pyc
_pyc = r'd:\PycharmProjects\AiSpiderProject\starmaker\__pycache__\tools.cpython-312.pyc'
_loader = SourcelessFileLoader('tools', _pyc)
_spec = importlib.util.spec_from_loader('tools', _loader)
assert _spec is not None
tools = importlib.util.module_from_spec(_spec)
_loader.exec_module(tools)

TARGET_USER_ID = 3634361573
NO_PROXY = {'http': None, 'https': None}  # bypass system proxy


def call_api(url: str, params: Dict[str, Any], proxies: Optional[Dict[str, Any]] = None):
    headers = tools.create_params(url=url, params=params)
    return requests.get(url, headers=headers, params=params, verify=False, timeout=30, proxies=proxies)


print('proxy env:', {k: v for k, v in os.environ.items() if 'proxy' in k.lower()})


def show(tag, resp):
    print(f'[{tag}] HTTP {resp.status_code}')
    try:
        body = resp.json()
        print(f'  body: {json.dumps(body, ensure_ascii=False)[:400]}')
    except Exception:
        print(f'  body(raw): {resp.text[:400]}')
    print(f'  final url host: {resp.url}')


url = f"https://api.starmakerstudios.com/api/v17/android/sm/us/phone/xhdpi/users/profile/{TARGET_USER_ID}"
params = {
    "phone_brand": "samsung",
    "phone_model": "SM-G9810",
    "phone_manufacturer": "samsung",
    "performance_level": "2",
}

# A: with system proxy (default)
try:
    show('via-system-proxy', call_api(url, params))
except Exception as e:
    print(f'[via-system-proxy] EXC: {type(e).__name__}: {str(e)[:200]}')

# B: direct (no proxy)
try:
    show('direct-no-proxy', call_api(url, params, proxies=NO_PROXY))
except Exception as e:
    print(f'[direct-no-proxy] EXC: {type(e).__name__}: {str(e)[:200]}')

# C: recordings endpoint direct
url2 = f"https://api.starmakerstudios.com/api/v17/android/sm/en/phone/xhdpi/users/{TARGET_USER_ID}/recordings"
params2 = {"next_cursor": 0, "skip_id": 0}
try:
    show('recordings-direct', call_api(url2, params2, proxies=NO_PROXY))
except Exception as e:
    print(f'[recordings-direct] EXC: {type(e).__name__}: {str(e)[:200]}')
