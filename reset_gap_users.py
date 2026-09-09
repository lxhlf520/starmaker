#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Description: Reset failed/interrupted users back to pending so the next --full run
              re-collects them. Safe: recording insert dedup relies on the unique
              index (owner_user_id, recording.sm_id), so re-runs never duplicate.
@Usage:       python reset_gap_users.py 3634536249 3634489022   # specific users
              python reset_gap_users.py --failed                # all status=2 users
              python reset_gap_users.py --all                   # EVERY user back to pending
"""
import sys

from db_config import MONGO_DB, MONGO_URI
from pymongo import MongoClient


def main() -> None:
    args = sys.argv[1:]
    db = MongoClient(MONGO_URI)[MONGO_DB]
    if args == ['--all']:
        res = db['creator_ids'].update_many({}, {'$set': {'status': 0}})
        print(f'reset ALL {res.modified_count} users to pending')
        return
    if args == ['--failed']:
        ids = [d['user_id'] for d in db['creator_ids'].find({'status': 2}, {'user_id': 1})]
    else:
        ids = []
        for a in args:               # creator_ids.user_id may be int or str, match both
            ids.append(a)
            if a.isdigit():
                ids.append(int(a))
    if not ids:
        print('nothing to reset (pass user_ids or --failed)')
        return
    res = db['creator_ids'].update_many({'user_id': {'$in': ids}}, {'$set': {'status': 0}})
    print(f'reset {res.modified_count} users to pending: {ids}')


if __name__ == '__main__':
    main()
