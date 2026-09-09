#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Show last N request-log rows to detect multi-instance interleaving."""
import csv
import sys

LOG = r'd:\PycharmProjects\AiSpiderProject\starmaker\request_log.csv'
n = int(sys.argv[1]) if len(sys.argv) > 1 else 25

rows = list(csv.DictReader(open(LOG, encoding='utf-8')))
print(f'last {n} of {len(rows)} requests (ts, user, cursor, status):')
for r in rows[-n:]:
    print(f"  {r['ts'][11:23]}  {r['user_id']}  cursor={r['cursor']}  {r['status']}")
