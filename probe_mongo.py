#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Probe local MongoDB: connectivity, auth, version."""
from pymongo import MongoClient

from db_config import MONGO_URI

for uri in [MONGO_URI, 'mongodb://localhost:27017/']:
    label = 'auth' if 'root' in uri else 'no-auth'
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        info = client.admin.command('ping')
        ver = client.admin.command('buildInfo')['version']
        dbs = client.list_database_names()
        print(f'[{label}] OK ping={info} version={ver} dbs={dbs}')
        break
    except Exception as e:
        print(f'[{label}] FAIL: {type(e).__name__}: {e}')
