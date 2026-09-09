#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Description: Direct connection (bypass proxy) vs system-proxy A/B test for Starmaker recordings API.
              Verifies whether the local broadband IP is 100% rejected.
"""
import importlib.util
import sys
import time
from pathlib import Path

import requests

DIR = Path(__file__).parent

# load tools.py by explicit path (project pyc/py module loader pattern)
_spec = importlib.util.spec_from_file_location('tools_mod', str(DIR / 'tools.py'))
assert _spec is not None and _spec.loader is not None
tools_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tools_mod)

URL_TMPL = 'https://api.starmakerstudios.com/api/v17/android/sm/en/phone/xhdpi/users/{uid}/recordings'
PARAMS = {'next_cursor': 0, 'skip_id': 0}

# test users: one known-good (3634361573) + a couple of pending from batch run
TEST_USERS = [3634361573, 3634547580, 3634550001]

DIRECT_ATTEMPTS = 3   # direct requests per user
PROXY_ATTEMPTS = 2    # proxied requests per user


def fetch(uid: int, sess: requests.Session, label: str) -> int:
    url = URL_TMPL.format(uid=uid)
    headers = tools_mod.create_params(PARAMS, url)
    t0 = time.time()
    try:
        r = sess.get(url, params=PARAMS, headers=headers, timeout=20)
        print(f'  {label:7s} uid={uid}  {r.status_code}  ({time.time() - t0:.1f}s)')
        return r.status_code
    except Exception as e:
        print(f'  {label:7s} uid={uid}  EXC {type(e).__name__}: {e}')
        return -1


def main():
    direct = requests.Session()
    direct.trust_env = False        # bypass system proxy -> true direct connection
    proxy = requests.Session()      # trust_env=True -> uses Windows system proxy

    print('=== DIRECT connection (no proxy) ===')
    d401 = d200 = 0
    for uid in TEST_USERS:
        for _ in range(DIRECT_ATTEMPTS):
            s = fetch(uid, direct, 'direct')
            if s == 401:
                d401 += 1
            elif s == 200:
                d200 += 1
            time.sleep(2)

    print('\n=== SYSTEM PROXY (for comparison) ===')
    p401 = p200 = 0
    for uid in TEST_USERS:
        for _ in range(PROXY_ATTEMPTS):
            s = fetch(uid, proxy, 'proxy')
            if s == 401:
                p401 += 1
            elif s == 200:
                p200 += 1
            time.sleep(2)

    n = d401 + d200
    print(f'\n=== RESULT ===')
    print(f'direct: {n} attempts, 200={d200}, 401={d401}'
          + (f'  -> 401 rate {d401 / n * 100:.0f}%' if n else ''))
    print(f'proxy : {p401 + p200} attempts, 200={p200}, 401={p401}')


if __name__ == '__main__':
    main()
