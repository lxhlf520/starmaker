#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Description: Analyze 401 intervals from request_log.csv.
              Answers: is 401 a rate-limit (periodic, tied to request rate)
              or proxy-node flapping (random bursts) -> do we need a better proxy?
"""
import csv
import statistics
from collections import Counter
from datetime import datetime

LOG = r'd:\PycharmProjects\AiSpiderProject\starmaker\request_log.csv'


def main():
    rows = []
    with open(LOG, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows.append(r)
    if not rows:
        print('no request_log.csv data yet')
        return

    total = len(rows)
    by_status = Counter(r['status'] for r in rows)
    print(f'total requests logged : {total}')
    print('status breakdown      : ' + ', '.join(f'{k}:{v}' for k, v in sorted(by_status.items())))

    # ---- 401 events in chronological order ----
    ev = sorted((datetime.fromisoformat(r['ts']), r['user_id'], int(r['cursor']))
                for r in rows if r['status'] == '401')
    span_min = (ev[-1][0] - ev[0][0]).total_seconds() / 60 if len(ev) >= 2 else 0
    print(f'401 events            : {len(ev)}  ({len(ev) / total * 100:.1f}% of requests)')

    # ---- intervals between consecutive 401 events ----
    if len(ev) >= 2:
        gaps = sorted((ev[i + 1][0] - ev[i][0]).total_seconds() for i in range(len(ev) - 1))

        def pct(p):
            return gaps[min(len(gaps) - 1, int(len(gaps) * p))]

        print(f'\n401-to-401 interval (n={len(gaps)}, window {span_min:.0f} min):')
        print(f'  min={gaps[0]:.1f}s  p25={pct(0.25):.1f}s  median={statistics.median(gaps):.1f}s  '
              f'p75={pct(0.75):.1f}s  p90={pct(0.90):.1f}s  max={gaps[-1]:.1f}s  '
              f'mean={statistics.mean(gaps):.1f}s')

        # ---- burst depth: how many 401s in a row for the same (user, cursor) ----
        bursts = Counter((uid, cur) for _, uid, cur in ev)
        dist = Counter(bursts.values())
        print('burst depth (401s per page before success): ' +
              ', '.join(f'{k}x401: {v} pages' for k, v in sorted(dist.items())))

        # ---- successes between consecutive 401s ----
        timeline = sorted((datetime.fromisoformat(r['ts']), r['status']) for r in rows)
        ok_between, cnt = [], 0
        for _, s in timeline:
            if s == '401':
                ok_between.append(cnt)
                cnt = 0
            else:
                cnt += 1
        print(f'\nsuccesses between consecutive 401s:')
        print(f'  min={min(ok_between)}  median={statistics.median(ok_between):.0f}  '
              f'mean={statistics.mean(ok_between):.1f}  max={max(ok_between)}')

    # ---- per-minute histogram ----
    per_min = Counter(t.strftime('%H:%M') for t, _, _ in ev)
    print('\n401 events per minute:')
    for m in sorted(per_min):
        bar = '#' * per_min[m]
        print(f'  {m}  {per_min[m]:3d} {bar}')

    # ---- verdict hints ----
    print('\nverdict hints:')
    if by_status.get('429', 0) == 0:
        print('  - zero HTTP 429: server is NOT applying classic rate limiting at this pace '
              '(1.5s/page, 1s/user)')
    if ev:
        print(f'  - 401 share {len(ev) / total * 100:.1f}% with random spacing -> proxy-node flapping '
              f'if gaps show no periodicity; consider a dedicated/stable node if burst depth grows')


if __name__ == '__main__':
    main()
