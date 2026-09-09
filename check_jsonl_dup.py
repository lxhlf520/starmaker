#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check works_trial.jsonl for duplicate sm_id rows (multi-instance double-write)."""
import json
from collections import Counter
from pathlib import Path

JSONL = Path(__file__).parent / 'works_trial.jsonl'

ids = Counter()
bad = 0
for line in open(JSONL, encoding='utf-8'):
    line = line.strip()
    if not line:
        continue
    try:
        rec = json.loads(line)
        rid = (rec.get('owner_user_id'), (rec.get('recording') or {}).get('id'))
        ids[rid] += 1
    except json.JSONDecodeError:
        bad += 1  # torn line from concurrent appends

total = sum(ids.values())
dup = {k: v for k, v in ids.items() if v > 1}
print(f'lines={total}  unique sm_id={len(ids)}  duplicate sm_id={len(dup)}  torn lines={bad}')
if dup:
    print('top duplicated ids:', list(dup.items())[:5])
    print(f'duplicate rows to drop: {total - len(ids)}')
