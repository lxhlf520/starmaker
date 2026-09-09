#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Description: Progress & effectiveness report for batch_collect.py run (MongoDB version).
              creator_ids status counts, data gaps, per-request retry recovery, throughput.
"""
import csv
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from pymongo import MongoClient

from db_config import MONGO_DB, MONGO_URI

DIR = Path(__file__).parent
LOG = DIR / 'request_log.csv'
RECENT_MIN = 20  # stats window


def mongo_stats():
    db = MongoClient(MONGO_URI)[MONGO_DB]
    creators = db['creator_ids']
    works = db['recording']
    status_map = {0: 'pending', 1: 'done', 2: 'failed'}
    print('== Mongo creator_ids status ==')
    for s in creators.aggregate([{'$group': {'_id': '$status', 'n': {'$sum': 1}}}, {'$sort': {'_id': 1}}]):
        print(f'  {status_map.get(s["_id"], s["_id"]):8s}: {s["n"]}')
    print('  done-with-gap users (need top-up later):')
    gap_n = 0
    for d in creators.find({'status': 1,
                            '$expr': {'$lt': ['$collected_works', '$total_works']}},
                           {'user_id': 1, 'total_works': 1, 'collected_works': 1}
                           ).sort([('total_works', -1)]):
        gap_n += 1
        if gap_n <= 10:
            miss = d['total_works'] - d['collected_works']
            print(f'    {d["user_id"]}: {d["collected_works"]}/{d["total_works"]} (missing {miss})')
    if gap_n > 10:
        print(f'    ... and {gap_n - 10} more')
    if gap_n == 0:
        print('    none')
    done = creators.count_documents({'status': 1})
    pipeline = [{'$match': {'status': 1}}, {'$group': {'_id': None, 'sum': {'$sum': '$collected_works'}}}]
    agg = list(creators.aggregate(pipeline))
    works_sum = agg[0]['sum'] if agg else 0
    print(f'  done users: {done}, collected works sum: {works_sum}')
    print(f'  recording collection total: {works.count_documents({})} docs')


def log_stats():
    if not LOG.exists():
        print('no request_log.csv')
        return
    rows = list(csv.DictReader(open(LOG, encoding='utf-8')))
    if not rows:
        return
    # tuple list avoids dict[str, str] type inference issues
    parsed = [(datetime.fromisoformat(r['ts']), r['status'], r['user_id'], r['cursor']) for r in rows]
    newest = max(t[0] for t in parsed)
    cutoff = newest - timedelta(minutes=RECENT_MIN)
    recent = [t for t in parsed if t[0] >= cutoff]
    c = Counter(t[1] for t in recent)
    n = len(recent)
    print(f'\n== last {RECENT_MIN} min (newest {newest:%H:%M}) ==')
    if n:
        print(f'  requests={n}  200={c["200"]}  401={c["401"]}  other={n - c["200"] - c["401"]}'
              f'  -> 401 rate {c["401"] / n * 100:.1f}%')
        span = (newest - min(t[0] for t in recent)).total_seconds() / 60
        if span > 0:
            print(f'  throughput: {n / span:.1f} req/min, {c["200"] / span:.1f} pages/min')

    # retry recovery: group by (user, cursor); pages that saw 401 - did they eventually 200?
    grp = defaultdict(list)
    for _, status, uid, cur in recent:
        grp[(uid, cur)].append(status)
    pages_with_401 = [v for v in grp.values() if '401' in v]
    recovered = sum(1 for v in pages_with_401 if '200' in v)
    if pages_with_401:
        print(f'  retry recovery: {recovered}/{len(pages_with_401)} pages with 401 eventually succeeded '
              f'({recovered / len(pages_with_401) * 100:.0f}%)')

    # full-log 401 rate for reference
    cf = Counter(t[1] for t in parsed)
    print(f'  full-log: {len(parsed)} reqs, 401 rate {cf["401"] / len(parsed) * 100:.1f}%')


if __name__ == '__main__':
    mongo_stats()
    log_stats()
