#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Description: Collect all works (recordings) of a Starmaker user by user_id.
              Page through users/{uid}/recordings, dedupe by sm_id, save to JSONL.
              Resume support: skips sm_ids already present in output file.
@Usage:       python collect_user_works.py [user_id]
"""
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from importlib.machinery import SourcelessFileLoader
from typing import Any, Dict, List, Optional, Set

import requests

# ---- Load tools.py (OAuth 1.0 signing, same module used by starmaker.py) ----
_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_PATH = os.path.join(_DIR, 'tools.py')
_PYC_PATH = os.path.join(_DIR, '__pycache__', 'tools.cpython-312.pyc')

if os.path.exists(_TOOLS_PATH):  # real source preferred
    _spec = importlib.util.spec_from_file_location('starmaker_tools', _TOOLS_PATH)
else:  # fallback: bytecode only
    _spec = importlib.util.spec_from_file_location('starmaker_tools', _PYC_PATH,
                                                   loader=SourcelessFileLoader('starmaker_tools', _PYC_PATH))
assert _spec is not None and _spec.loader is not None
tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tools)

BASE = 'https://api.starmakerstudios.com/api/v17/android/sm/en/phone/xhdpi'
PAGE_SIZE = 15
PAGE_DELAY = 1.5          # seconds between pages, be polite to the API
MAX_CONSECUTIVE_ERRORS = 5
AUTH_RETRY_LIMIT = 4      # 401/403 may be proxy-node flapping; retry with backoff


class UserWorksCollector:
    def __init__(self, user_id: int, output_file: str, verify: bool = False):
        self.user_id = user_id
        self.output_file = output_file
        self.verify = verify
        self.session = requests.Session()
        self.seen_sm_ids: Set[str] = set()
        self.collected: List[Dict[str, Any]] = []
        self.total_hint: Optional[int] = None
        self._load_existing()

    def _load_existing(self):
        """Resume: load sm_ids from existing output file so we skip duplicates."""
        if not os.path.exists(self.output_file):
            return
        try:
            with open(self.output_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    sm_id = (rec.get('recording') or {}).get('sm_id')
                    if sm_id:
                        self.seen_sm_ids.add(str(sm_id))
            print(f'[resume] {len(self.seen_sm_ids)} works already in {self.output_file}')
        except Exception as e:
            print(f'[resume] failed to read existing file: {e}')

    def fetch_page(self, next_cursor: int, skip_id: int = 0) -> Dict[str, Any]:
        url = f'{BASE}/users/{self.user_id}/recordings'
        params = {'next_cursor': next_cursor, 'skip_id': skip_id}
        headers = tools.create_params(url=url, params=params)
        resp = self.session.get(url, headers=headers, params=params,
                                verify=self.verify, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def collect(self) -> List[Dict[str, Any]]:
        next_cursor = 0
        consecutive_errors = 0
        auth_retries = 0
        new_count = 0
        mode = 'a' if self.seen_sm_ids else 'w'
        start_time = time.time()

        while True:
            try:
                data = self.fetch_page(next_cursor)
                consecutive_errors = 0
                auth_retries = 0
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else '?'
                auth_retries += 1
                print(f'[error] page cursor={next_cursor} HTTP {code} '
                      f'(auth retry {auth_retries}/{AUTH_RETRY_LIMIT})')
                if str(code) in ('401', '403'):
                    if auth_retries >= AUTH_RETRY_LIMIT:
                        print('[fatal] 401/403 persist after retries - token rejected. '
                              'Check local proxy node is alive/switch node, and token validity.')
                        break
                    wait = 5 * auth_retries
                    print(f'        proxy-node flapping suspected, waiting {wait}s then retrying same page...')
                    time.sleep(wait)
                    continue
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print('[fatal] too many consecutive errors, stop.')
                    break
                time.sleep(2 ** consecutive_errors)
                continue
            except requests.RequestException as e:
                print(f'[error] network: {e}')
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print('[fatal] too many consecutive errors, stop.')
                    break
                time.sleep(2 ** consecutive_errors)
                continue

            self.total_hint = data.get('total', self.total_hint)
            recording_list = data.get('recording_list', [])
            if not recording_list:
                print(f'[done] empty recording_list at cursor={next_cursor}, stop.')
                break

            batch_new = []
            with open(self.output_file, mode, encoding='utf-8') as f:
                for record in recording_list:
                    rec = record.get('recording') or {}
                    sm_id = str(rec.get('sm_id') or '')
                    if not sm_id or sm_id in self.seen_sm_ids:
                        continue
                    self.seen_sm_ids.add(sm_id)
                    record['owner_user_id'] = str(self.user_id)
                    record['collected_at'] = datetime.now(timezone.utc).isoformat()
                    batch_new.append(record)
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')

            self.collected.extend(batch_new)
            new_count += len(batch_new)
            known = len(self.seen_sm_ids)
            total = self.total_hint or '?'
            print(f'[page cursor={next_cursor}] got {len(recording_list)} items, '
                  f'new {len(batch_new)} | progress {known}/{total}')

            # Stop conditions
            if self.total_hint and known >= self.total_hint:
                print(f'[done] collected all {known}/{self.total_hint} works.')
                break
            if known > 0 and len(recording_list) < PAGE_SIZE and known >= (self.total_hint or 0):
                print('[done] reached last page.')
                break

            next_cursor += PAGE_SIZE
            mode = 'a'
            time.sleep(PAGE_DELAY)

        elapsed = time.time() - start_time
        print('=' * 50)
        print(f'collected {new_count} new works for user {self.user_id} '
              f'in {elapsed:.1f}s -> {self.output_file}')
        print(f'total known sm_ids now: {len(self.seen_sm_ids)} (server total: {self.total_hint})')
        return self.collected


def main():
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 3634361573
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       f'works_{user_id}.jsonl')
    collector = UserWorksCollector(user_id, out)
    collector.collect()


if __name__ == '__main__':
    main()
