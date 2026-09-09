#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Full python process dump + latest request log lines (to find hidden collector instances)."""
import csv
from datetime import datetime

import psutil

print('== all python processes ==')
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        name = (p.info.get('name') or '').lower()
        if 'python' not in name:
            continue
        cmd = ' '.join(p.info.get('cmdline') or [])
        print(f'  {p.info["pid"]:6d}  {cmd[:140]}')
    except Exception as e:
        print(f'  <error {type(e).__name__}>')

print('\n== request_log.csv latest lines ==')
LOG = r'd:\PycharmProjects\AiSpiderProject\starmaker\request_log.csv'
rows = list(csv.DictReader(open(LOG, encoding='utf-8')))
print(f'total rows: {rows and len(rows)}')
for r in rows[-5:]:
    print(f'  {r["ts"]}  {r["user_id"]}  cursor={r["cursor"]}  {r["status"]}')
if rows:
    age = (datetime.now() - datetime.fromisoformat(rows[-1]['ts'])).total_seconds()
    print(f'latest log age: {age:.0f}s ago')
