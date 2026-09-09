#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnose done-with-gap users: was collection cut by retry-exhaustion or is total inflated?"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

DIR = Path(__file__).parent
LOG = DIR / 'request_log.csv'
DEFAULT = ['3634536249', '3634489022', '3634455255', '3634458661', '3634565393']
GAP_USERS = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT

rows = list(csv.DictReader(open(LOG, encoding='utf-8')))
by_user = defaultdict(list)
for r in rows:
    by_user[r['user_id']].append(r)

for uid in GAP_USERS:
    rs = by_user.get(uid, [])
    if not rs:
        print(f'{uid}: no requests in log')
        continue
    statuses = [r['status'] for r in rs]
    last = rs[-1]
    # requests after last 401
    last401_idx = max((i for i, s in enumerate(statuses) if s == '401'), default=-1)
    tail = rs[last401_idx + 1:] if last401_idx >= 0 else rs
    tail_ok = all(s == '200' for s in [t['status'] for t in tail])
    print(f'{uid}: {len(rs)} reqs, last401={rs[last401_idx]["ts"][11:19] if last401_idx >= 0 else "none"}, '
          f'last req cursor={last["cursor"]} status={last["status"]}, '
          f'after-last-401 all-200={tail_ok and len(tail) > 0}, tail_len={len(tail)}')
