#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Description: Migrate JSONL work records -> MongoDB starmaker.recording collection (one-time).
              Unique index (owner_user_id, recording.id) gives idempotent dedup; safe to re-run.
"""
import json
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import BulkWriteError

from db_config import MONGO_URI

FILES = [
    Path(__file__).parent / 'works_trial.jsonl',
    Path(__file__).parent / 'works_3634361573.jsonl',
]

client = MongoClient(MONGO_URI)
db = client['starmaker']
coll = db['recording']
coll.create_index([('owner_user_id', 1), ('recording.id', 1)], unique=True)

docs, torn = [], 0
for f in FILES:
    for line in open(f, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            docs.append(json.loads(line))
        except json.JSONDecodeError:
            torn += 1
print(f'parsed {len(docs)} docs (torn lines: {torn})')

try:
    result = coll.insert_many(docs, ordered=False)
    print(f'inserted: {len(result.inserted_ids)}')
except BulkWriteError as e:
    dupes = sum(1 for err in e.details['writeErrors'] if err['code'] == 11000)
    other = [err for err in e.details['writeErrors'] if err['code'] != 11000]
    print(f'bulk insert: {e.details["nInserted"]} new inserted, {dupes} duplicates skipped')
    if other:
        print(f'NON-DUPLICATE ERRORS: {other[:3]}')

total = coll.count_documents({})
print(f'starmaker.recording total: {total}')
