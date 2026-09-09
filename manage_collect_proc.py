#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""List or kill batch_collect.py processes.

NOTE: .venv python.exe is a launcher that spawns the real base interpreter (Python312)
as a CHILD process. They always appear as a PAIR with the same start time - this is ONE
collector, not two. Killing either kills the run. Group by start time to read it right.
"""
import sys
from datetime import datetime

import psutil


def find_collectors():
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            cmd = ' '.join(p.info.get('cmdline') or [])
            if 'batch_collect.py' in cmd and 'python' in (p.info.get('name') or '').lower():
                procs.append((p.info['pid'], p.info['create_time'], cmd, p))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return procs


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'list'
    procs = find_collectors()
    if not procs:
        print('no batch_collect processes running')
        return
    # group by start time (launcher + real interpreter share it)
    groups = {}
    for pid, ctime, cmd, p in procs:
        groups.setdefault(round(ctime), []).append((pid, cmd))
    for ctime, members in sorted(groups.items()):
        pids = [pid for pid, _ in members]
        print(f'collector group @ {datetime.fromtimestamp(ctime):%H:%M:%S} '
              f'(ONE run, {len(members)} procs: launcher + interpreter) -> PIDs {pids}')
        for pid, cmd in members:
            print(f'   {pid}: {cmd[:110]}')
        if action == 'kill':
            for pid, _ in members:
                try:
                    psutil.Process(pid).terminate()
                    print(f'   -> terminated {pid}')
                except psutil.NoSuchProcess:
                    pass


if __name__ == '__main__':
    main()
