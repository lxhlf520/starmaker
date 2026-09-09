#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Description: Fix recording collection unique index: (owner_user_id, recording.sm_id) is the
              true dedup key (sm_id = work id, recording.id = resource id). Drops the wrong
              index, dedups by sm_id keeping the first doc, recreates the correct index.
"""
from pymongo import MongoClient

from db_config import MONGO_URI

client = MongoClient(MONGO_URI)
coll = client['starmaker']['recording']

# 1) drop wrong index
for idx in coll.list_indexes():
    keys = list(idx['key'].items())
    if keys == [('owner_user_id', 1), ('recording.id', 1)]:
        coll.drop_index(idx['name'])
        print(f"dropped wrong index {idx['name']}")

# 2) dedup by (owner_user_id, sm_id), keep first _id per group
removed = 0
pipeline = [
    {'$group': {'_id': {'o': '$owner_user_id', 's': '$recording.sm_id'},
                'ids': {'$push': '$_id'}, 'n': {'$sum': 1}}},
    {'$match': {'n': {'$gt': 1}}},
]
for grp in coll.aggregate(pipeline, allowDiskUse=True):
    keep = grp['ids'][0]
    res = coll.delete_many({'_id': {'$in': grp['ids'][1:]}})
    removed += res.deleted_count
print(f'duplicates removed by (owner_user_id, sm_id): {removed}')

# 3) correct unique index
name = coll.create_index([('owner_user_id', 1), ('recording.sm_id', 1)], unique=True)
print(f'created unique index: {name}')

# 4) sanity: any null sm_id?
nulls = coll.count_documents({'recording.sm_id': None})
total = coll.count_documents({})
print(f'total docs: {total}, docs with null sm_id: {nulls}')
