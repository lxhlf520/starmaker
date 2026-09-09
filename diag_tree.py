#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Show batch_collect process tree: create time + parent chain."""
from datetime import datetime

import psutil

for p in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
    try:
        cmd = ' '.join(p.info.get('cmdline') or [])
        if 'batch_collect' not in cmd:
            continue
        print(f'PID {p.info["pid"]}  start={datetime.fromtimestamp(p.info["create_time"]):%H:%M:%S}')
        print(f'  cmd   : {cmd[:130]}')
        pr = p.parent()
        if pr is not None:
            pcmd = ' '.join(pr.info.get('cmdline') or []) if pr.info.get('cmdline') else pr.info.get('name')
            print(f'  parent: PID {pr.pid} [{pr.info.get("name")}] {str(pcmd)[:110]}')
        else:
            print('  parent: <none>')
    except Exception as e:
        print(f'  err {type(e).__name__}: {e}')
