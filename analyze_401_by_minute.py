#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Description: Per-minute 401 rate from request_log.csv - to verify proxy node switch effect.
              Prints every minute window: requests / 200 / 401 / 401-rate, plus overall since a cutoff.
"""
import csv
import sys
from collections import Counter
from datetime import datetime, timedelta

LOG = r'd:\PycharmProjects\AiSpiderProject\starmaker\request_log.csv'


def main():
    last_n_min = int(sys.argv[1]) if len(sys.argv) > 1 else 20  # only show recent N minutes
    rows = []
    with open(LOG, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            r['dt'] = datetime.fromisoformat(r['ts'])
            rows.append(r)
    if not rows:
        print('no data')
        return

    newest = max(r['dt'] for r in rows)
    cutoff = newest - timedelta(minutes=last_n_min)
    recent = [r for r in rows if r['dt'] >= cutoff]

    print(f'log span: {min(r["dt"] for r in rows):%H:%M:%S} -> {newest:%H:%M:%S}  '
          f'(total {len(rows)} requests)')
    print(f'\nper-minute view (last {last_n_min} min):')
    print('  minute  reqs   200   401  other  401-rate')
    by_min = {}
    for r in recent:
        key = r['dt'].strftime('%H:%M')
        d = by_min.setdefault(key, {'req': 0, '200': 0, '401': 0, 'other': 0})
        d['req'] += 1
        d[r['status'] if r['status'] in ('200', '401') else 'other'] += 1
    for m in sorted(by_min):
        d = by_min[m]
        rate = d['401'] / d['req'] * 100 if d['req'] else 0
        bar = '#' * int(rate / 5)
        print(f'  {m}   {d["req"]:4d}  {d["200"]:4d}  {d["401"]:4d}  {d["other"]:4d}   {rate:5.1f}% {bar}')

    # overall recent window
    c = Counter(r['status'] for r in recent)
    total = len(recent)
    if total:
        print(f'\nrecent {last_n_min} min overall: reqs={total}, 200={c["200"]}, 401={c["401"]}, '
              f'other={total - c["200"] - c["401"]}, 401-rate={c["401"] / total * 100:.1f}%')


if __name__ == '__main__':
    main()
