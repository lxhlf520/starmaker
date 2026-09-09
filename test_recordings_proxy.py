#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Description: Probe recordings endpoint via system proxy - inspect response structure
"""
import importlib.util
import json
from importlib.machinery import SourcelessFileLoader

import requests

_pyc = r'd:\PycharmProjects\AiSpiderProject\starmaker\__pycache__\tools.cpython-312.pyc'
_loader = SourcelessFileLoader('tools', _pyc)
_spec = importlib.util.spec_from_loader('tools', _loader)
assert _spec is not None
tools = importlib.util.module_from_spec(_spec)
_loader.exec_module(tools)

UID = 3634361573


def fetch(uid, next_cursor, skip_id=0):
    url = f'https://api.starmakerstudios.com/api/v17/android/sm/en/phone/xhdpi/users/{uid}/recordings'
    params = {'next_cursor': next_cursor, 'skip_id': skip_id}
    headers = tools.create_params(url=url, params=params)
    return requests.get(url, headers=headers, params=params, verify=False, timeout=30)


def main():
    resp = fetch(UID, 0)
    print('HTTP', resp.status_code)
    try:
        data = resp.json()
    except Exception:
        print('non-JSON body:', resp.text[:300])
        return

    print('top keys:', list(data.keys()))
    print('total:', data.get('total'))
    print('next_cursor field:', repr(data.get('next_cursor')))
    rl = data.get('recording_list', [])
    print('recording_list size:', len(rl))
    if rl:
        first = rl[0]
        print('record keys:', list(first.keys()))
        rec = first.get('recording', {})
        print('recording keys:', list(rec.keys())[:40])
        brief = {k: rec.get(k) for k in ('sm_id', 'raw_text', 'num_comments', 'num_likes',
                                         'num_plays', 'create_time', 'web_url')}
        print(json.dumps(brief, ensure_ascii=False, indent=1))

    # page 2 probe
    print()
    resp2 = fetch(UID, 15)
    print('page2 HTTP', resp2.status_code)
    data2 = resp2.json()
    rl2 = data2.get('recording_list', [])
    print('page2 total:', data2.get('total'), 'size:', len(rl2))
    if rl:
        id1 = rl[0].get('recording', {}).get('sm_id')
        id2 = rl2[0].get('recording', {}).get('sm_id') if rl2 else None
        print(f'page1 first sm_id={id1}, page2 first sm_id={id2}, different={id1 != id2}')


if __name__ == '__main__':
    main()
