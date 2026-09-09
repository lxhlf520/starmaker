#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Description: Central MongoDB connection settings for all starmaker scripts.
              Reads config.ini next to this file (create it from config.example.ini).
              config.ini is git-ignored so real credentials never enter the repo.
"""
import configparser
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, 'config.ini')


def _load() -> configparser.ConfigParser:
    if not os.path.exists(_CONFIG_PATH):
        raise SystemExit(
            '[db_config] config.ini not found in %s\n'
            '[db_config] Copy config.example.ini -> config.ini and fill in your MongoDB settings.' % _DIR
        )
    # interpolation=None: Mongo URIs contain URL-encoded chars like %23 (for '#')
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(_CONFIG_PATH, encoding='utf-8')
    if not cp.has_section('mongodb') or not cp.get('mongodb', 'uri', fallback='').strip():
        raise SystemExit('[db_config] config.ini missing [mongodb] uri. See config.example.ini.')
    return cp


_cfg = _load()
MONGO_URI = _cfg.get('mongodb', 'uri').strip()
MONGO_DB = _cfg.get('mongodb', 'db', fallback='starmaker').strip() or 'starmaker'

if __name__ == '__main__':
    # Connectivity self-check: python db_config.py
    from pymongo import MongoClient
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    info = client.admin.command('ping')
    print(f'MONGO_DB  = {MONGO_DB}')
    print(f'ping      = {info}')
    print(f'databases = {client.list_database_names()}')
    client.close()
