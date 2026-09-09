#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Description: Batch-collect Starmaker user works driven by MongoDB 'starmaker.creator_ids'.
              Modes:
                --probe N   : fetch page 1 for first N pending users only (rate-limit probe)
                --full N    : fully collect works for first N pending users (default 100)
              Works are stored directly in MongoDB 'starmaker.recording'; dedup relies on the
              unique index (owner_user_id, recording.sm_id) instead of JSONL seen-sets, so the
              run is resumable and idempotent. owner_user_id is stored as str (matches migrated docs).
@Usage:       python batch_collect.py --probe 100
              python batch_collect.py --full 100
"""
import argparse
import csv
import importlib.util
import os
import time
from datetime import datetime, timezone
from importlib.machinery import SourcelessFileLoader
from typing import Any, Dict, List, Optional, Tuple

import requests
from pymongo import MongoClient
from pymongo.errors import BulkWriteError

from db_config import MONGO_DB, MONGO_URI

# Load tools.py explicitly from this directory (OAuth 1.0 signing)
_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_SRC = os.path.join(_DIR, 'tools.py')
if os.path.exists(_TOOLS_SRC):
    _spec = importlib.util.spec_from_file_location('starmaker_tools', _TOOLS_SRC)
else:
    _pyc = os.path.join(_DIR, '__pycache__', 'tools.cpython-312.pyc')
    _spec = importlib.util.spec_from_file_location('starmaker_tools', _pyc,
                                                   loader=SourcelessFileLoader('starmaker_tools', _pyc))
assert _spec is not None and _spec.loader is not None
tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tools)

# ---- Config ----
BASE = 'https://api.starmakerstudios.com/api/v17/android/sm/en/phone/xhdpi'
PAGE_SIZE = 15
PAGE_DELAY = 1.5          # between pages of the same user
USER_DELAY = 1.0          # between users
RETRY_WAITS = [5, 10, 15, 20, 30]   # seconds for 401/403 flapping
RETRY_429_WAITS = [15, 30, 60]      # seconds for 429 rate-limit
VERIFY = False
DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(DIR, 'request_log.csv')   # per-request log for 401 interval analysis


class RequestStats:
    """Global request-level statistics for rate-limit analysis."""

    def __init__(self):
        self.status_counts: Dict[str, int] = {}
        self.retried_pages = 0
        self.retry_success = 0
        self.retry_exhausted = 0
        self.rate_limit_hits_429 = 0
        self.latencies: List[float] = []
        self.t0 = time.time()

    def record(self, status: int, latency: float):
        key = str(status)
        self.status_counts[key] = self.status_counts.get(key, 0) + 1
        self.latencies.append(latency)

    def report(self) -> str:
        elapsed = time.time() - self.t0
        total = sum(self.status_counts.values())
        avg_lat = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        lines = [
            '=' * 60,
            'RATE-LIMIT / REQUEST REPORT',
            '=' * 60,
            f'total requests        : {total}',
            f'elapsed               : {elapsed:.0f}s  ({total / elapsed:.2f} req/s avg)',
            f'avg latency           : {avg_lat:.2f}s',
            f'requests retried      : {self.retried_pages} (recovered: {self.retry_success}, '
            f'exhausted: {self.retry_exhausted})',
            f'HTTP 429 rate-limit   : {self.rate_limit_hits_429}',
            'status breakdown      : ' + ', '.join(f'{k}:{v}' for k, v in sorted(self.status_counts.items())),
        ]
        return '\n'.join(lines)


def _log_request(uid: int, cursor: int, status: int, latency: float):
    """Append one row per HTTP attempt (timestamped) for 401-interval analysis."""
    exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(['ts', 'user_id', 'cursor', 'status', 'latency_s'])
        w.writerow([datetime.now().isoformat(timespec='milliseconds'), uid, cursor,
                    status, f'{latency:.3f}'])


def fetch_page(session: requests.Session, uid: int, next_cursor: int) -> Tuple[int, Optional[Dict[str, Any]]]:
    """Single request with signed headers. Returns (status, json_or_None). Never raises for HTTP status."""
    url = f'{BASE}/users/{uid}/recordings'
    params = {'next_cursor': next_cursor, 'skip_id': 0}
    headers = tools.create_params(url=url, params=params)
    t0 = time.time()
    try:
        resp = session.get(url, headers=headers, params=params, verify=VERIFY, timeout=30)
        latency = time.time() - t0
        try:
            data = resp.json()
        except ValueError:
            data = None
        _log_request(uid, next_cursor, resp.status_code, latency)
        return resp.status_code, data
    except requests.RequestException:
        _log_request(uid, next_cursor, -1, time.time() - t0)
        return -1, None


def fetch_page_with_retry(session, uid, next_cursor, stats: RequestStats) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Request with retry on 401/403 (node flapping) and 429 (rate limit)."""
    all_waits = {'auth': RETRY_WAITS, 'rl': RETRY_429_WAITS}
    auth_tries = 0
    rl_tries = 0
    while True:
        status, data = fetch_page(session, uid, next_cursor)
        if status == -1:
            stats.record(0, 30.0)
            return None, 'network-error'
        stats.record(status, 0)
        if status == 200:
            return data, None

        if status == 429:
            stats.rate_limit_hits_429 += 1
            if rl_tries >= len(all_waits['rl']):
                stats.retry_exhausted += 1
                return None, f'429-exhausted after {rl_tries} retries'
            wait = all_waits['rl'][rl_tries]
            rl_tries += 1
            stats.retried_pages += 1
            print(f'    [429] rate-limited, backoff {wait}s (try {rl_tries})')
            time.sleep(wait)
            continue

        if status in (401, 403):
            if auth_tries >= len(all_waits['auth']):
                stats.retry_exhausted += 1
                return None, f'{status}-exhausted after {auth_tries} retries'
            wait = all_waits['auth'][auth_tries]
            auth_tries += 1
            stats.retried_pages += 1
            # Force a new TCP connection: the pooled one may be pinned to a bad egress IP
            session.close()
            print(f'    [{status}] retry in {wait}s with FRESH connection (try {auth_tries})')
            time.sleep(wait)
            continue

        return None, f'http-{status}'


# ---- MongoDB data access ----

def get_pending_users(db, limit: int) -> List[Tuple[int, int]]:
    cur = (db['creator_ids'].find({'status': 0}, {'user_id': 1, 'attempts': 1})
           .sort('user_id', 1).limit(limit))
    return [(d['user_id'], d.get('attempts', 0)) for d in cur]


def update_user_done(db, uid: int, total: Optional[int], collected: int):
    """collected = total docs now in Mongo for this user (accurate across resumes/top-ups)."""
    db['creator_ids'].update_one(
        {'user_id': uid},
        {'$set': {'status': 1, 'total_works': total or 0, 'collected_works': collected,
                  'collected_at': datetime.now(timezone.utc), 'last_error': None},
         '$inc': {'attempts': 1}})


def update_user_fail(db, uid: int, total: Optional[int], collected: int, err: str):
    db['creator_ids'].update_one(
        {'user_id': uid},
        {'$set': {'status': 2, 'total_works': total, 'collected_works': collected,
                  'last_error': err[:200]},
         '$inc': {'attempts': 1}})


def insert_recordings(db, uid: int, page_records: List[Dict[str, Any]]) -> int:
    """Insert a page's recordings; unique index (owner_user_id, recording.sm_id) dedups.
    Returns number of newly inserted docs."""
    if not page_records:
        return 0
    try:
        res = db['recording'].insert_many(page_records, ordered=False)
        return len(res.inserted_ids)
    except BulkWriteError as e:
        non_dup = [w for w in e.details.get('writeErrors', []) if w['code'] != 11000]
        if non_dup:
            raise RuntimeError(f'non-duplicate mongo write errors: {non_dup[:2]}') from e
        return int(e.details.get('nInserted', 0))


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--probe', type=int, metavar='N',
                      help='probe first N pending users: 1 request each, report totals & rate-limit')
    mode.add_argument('--full', type=int, metavar='N',
                      help='fully collect first N pending users')
    args = ap.parse_args()
    n = args.probe if args.probe else args.full
    probe_only = args.probe is not None

    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    creators = db['creator_ids']
    works = db['recording']

    users = get_pending_users(db, n)
    if not users:
        print('no pending users found (status=0)')
        return
    print(f'mode={"PROBE" if probe_only else "FULL"} | users this run: {len(users)}')

    stats = RequestStats()
    session = requests.Session()
    print(f'resume base: recording collection has {works.count_documents({})} docs '
          f'(dedup via unique index owner_user_id + recording.sm_id)')

    totals: List[int] = []
    ok = fail = 0

    if probe_only:
        for i, (uid, _) in enumerate(users, 1):
            data, err = fetch_page_with_retry(session, uid, 0, stats)
            if err:
                fail += 1
                update_user_fail(db, uid, None, 0, err)
                print(f'[{i}/{len(users)}] {uid} PROBE FAIL: {err}')
            else:
                total = data.get('total', 0) if data else 0
                totals.append(total)
                ok += 1
                creators.update_one({'user_id': uid}, {'$set': {'total_works': total}})
                print(f'[{i}/{len(users)}] {uid} total_works={total}')
            time.sleep(USER_DELAY)

        # probe summary
        if totals:
            totals_sorted = sorted(totals, reverse=True)
            print()
            print(f'probe ok={ok} fail={fail}')
            print(f'works total sum={sum(totals)}, avg={sum(totals) / len(totals):.0f}, '
                  f'max={totals_sorted[0]}, min={totals_sorted[-1]}')
            est_pages = sum(-(-t // PAGE_SIZE) for t in totals)
            print(f'estimated pages for these users: {est_pages} '
                  f'(~{est_pages * PAGE_DELAY / 60:.0f} min at {PAGE_DELAY}s/page)')
    else:
        for i, (uid, _) in enumerate(users, 1):
            t_user0 = time.time()
            uid_key = str(uid)
            cursor = 0
            new_this_run = 0
            user_total: Optional[int] = None
            err: Optional[str] = None
            empty_streak = 0
            while True:
                data, perr = fetch_page_with_retry(session, uid, cursor, stats)
                if perr:
                    err = perr
                    break
                user_total = data.get('total', user_total) if data else user_total
                rl = data.get('recording_list', []) if data else []
                if not rl:
                    empty_streak += 1
                    if empty_streak >= 1:
                        break
                page_docs = []
                for record in rl:
                    rec = record.get('recording') or {}
                    if not rec.get('sm_id'):
                        continue
                    record['owner_user_id'] = uid_key
                    record['collected_at'] = datetime.now(timezone.utc).isoformat()
                    page_docs.append(record)
                new_this_run += insert_recordings(db, uid, page_docs)

                known_for_user = works.count_documents({'owner_user_id': uid_key})
                if user_total and known_for_user >= user_total:
                    break
                cursor += PAGE_SIZE
                time.sleep(PAGE_DELAY)

            took = time.time() - t_user0
            known_total = works.count_documents({'owner_user_id': uid_key})
            if err and new_this_run == 0 and known_total == 0:
                fail += 1
                update_user_fail(db, uid, user_total, known_total, err)
                print(f'[{i}/{len(users)}] {uid} FAILED ({err}) user_total={user_total} took={took:.0f}s')
            else:
                ok += 1
                update_user_done(db, uid, user_total, known_total)
                tail = f' (partial, stopped on: {err})' if err else ''
                print(f'[{i}/{len(users)}] {uid} collected {known_total}/{user_total} '
                      f'works (+{new_this_run} new) in {took:.0f}s{tail}')
            time.sleep(USER_DELAY)

    print()
    print(stats.report())
    # final DB state
    for s in creators.aggregate([{'$group': {'_id': '$status', 'n': {'$sum': 1}}}, {'$sort': {'_id': 1}}]):
        print(f'status={s["_id"]}: {s["n"]} users')
    print(f'recording collection total: {works.count_documents({})} docs')
    client.close()
    session.close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        err = traceback.format_exc()
        with open(os.path.join(DIR, 'crash.log'), 'a', encoding='utf-8') as f:
            f.write(f'\n[{datetime.now().isoformat()}]\n{err}\n')
        print(err)
        raise
