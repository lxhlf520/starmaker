#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Description: Test Starmaker core APIs (users/profile, users/recordings) with tools.pyc
"""
import importlib.util
import json
import warnings
from importlib.machinery import SourcelessFileLoader
from typing import Any, Dict

import requests

# NOTE: keep verify=False to match starmaker.py behaviour (special cert chain); suppress warnings only
warnings.filterwarnings('ignore', category=UserWarning, module='urllib3')

# Load tools.pyc (source tools.py was lost, only bytecode remains)
_pyc = r'd:\PycharmProjects\AiSpiderProject\starmaker\__pycache__\tools.cpython-312.pyc'
_loader = SourcelessFileLoader('tools', _pyc)
_spec = importlib.util.spec_from_loader('tools', _loader)
assert _spec is not None
tools = importlib.util.module_from_spec(_spec)
_loader.exec_module(tools)

TARGET_USER_ID = 3634361573


def call_api(url: str, params: Dict[str, Any]) -> requests.Response:
    headers = tools.create_params(url=url, params=params)
    return requests.get(url, headers=headers, params=params, verify=False, timeout=30)


def main():
    # ---- Test 1: user profile ----
    print('=' * 60)
    print(f'[TEST 1] GET users/profile/{TARGET_USER_ID}')
    print('=' * 60)
    url1 = f"https://api.starmakerstudios.com/api/v17/android/sm/us/phone/xhdpi/users/profile/{TARGET_USER_ID}"
    params1 = {
        "phone_brand": "samsung",
        "phone_model": "SM-G9810",
        "phone_manufacturer": "samsung",
        "performance_level": "2",
    }
    try:
        resp = call_api(url1, params1)
        print(f'HTTP {resp.status_code}')
        data = resp.json()
        user = data.get('user') or {}
        print(f'keys: {list(data.keys())}')
        print(f'user keys: {list(user.keys())[:30]}')
        print(json.dumps({k: user.get(k) for k in
                          ('id', 'name', 'sm_id', 'num_followers', 'num_followees', 'num_recordings',
                           'num_likes_received', 'create_time')},
                         ensure_ascii=False, indent=1))
    except Exception as e:
        print(f'FAILED: {type(e).__name__}: {str(e)[:300]}')

    # ---- Test 2: user recordings (works list) ----
    print()
    print('=' * 60)
    print(f'[TEST 2] GET users/{TARGET_USER_ID}/recordings')
    print('=' * 60)
    url2 = f"https://api.starmakerstudios.com/api/v17/android/sm/en/phone/xhdpi/users/{TARGET_USER_ID}/recordings"
    params2 = {"next_cursor": 0, "skip_id": 0}
    try:
        resp = call_api(url2, params2)
        print(f'HTTP {resp.status_code}')
        data = resp.json()
        print(f'top-level keys: {list(data.keys())}')
        print(f'total: {data.get("total")}')
        rec_list = data.get('recording_list', [])
        print(f'recording_list size: {len(rec_list)}')
        if rec_list:
            first = rec_list[0]
            print(f'first record keys: {list(first.keys())}')
            rec = first.get('recording', {})
            print(json.dumps({k: rec.get(k) for k in
                              ('sm_id', 'raw_text', 'num_comments', 'num_likes', 'num_plays',
                               'create_time', 'web_url')}, ensure_ascii=False, indent=1))
    except Exception as e:
        print(f'FAILED: {type(e).__name__}: {str(e)[:300]}')


if __name__ == '__main__':
    main()
