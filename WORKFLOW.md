# Starmaker Collection Workflow

End-to-end pipeline of this project, from a bare server to a fully harvested works database.

```
Setup ──> Data Migration ──> Link Verification ──> Production Run ──> Monitoring ──> Maintenance ──> Scaling
```

## Phase 0 — Setup

```cmd
git clone https://github.com/lxhlf520/starmaker.git
cd starmaker
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt

copy config.example.ini config.ini
notepad config.ini          :: fill [mongodb] uri (URL-encode special chars, e.g. # -> %23) and db

.venv\Scripts\python db_config.py       :: must print ping = {'ok': 1.0}
.venv\Scripts\python probe_mongo.py     :: auth + version check
```

Requirements: Windows, Python 3.12+, MongoDB (local or remote), an HTTP system proxy
(the site is edge-blocked for datacenter/residential IPs — a working proxy is **mandatory**).

## Phase 1 — Data Migration

Two accepted starting states:

**A. Restore an existing database** (keeps collected works + progress):

```cmd
mongorestore --uri "mongodb://USER:PASS@TARGET:27017" --drop .\starmaker_backup\starmaker
```

Indexes are restored together with the data — verify them:

```js
db.recording.getIndexes()      // must contain { owner_user_id: 1, "recording.sm_id": 1, unique: true }
db.creator_ids.getIndexes()    // must contain { user_id: 1, unique: true }
```

If the restore reported duplicate-key errors, the cleanest fix is **state B** (skip the damaged
collection and re-collect from scratch — already- restored documents remain and act as dedup cache).

**B. Fresh start**: import only the `creator_ids` base table (users to collect), leave `recording`
empty, then reset progress:

```cmd
.venv\Scripts\python reset_gap_users.py --all      :: every user -> pending
```

## Phase 2 — Link Verification

```cmd
.venv\Scripts\python batch_collect.py --probe 5
```

Fetches page 1 for the first 5 pending users. `probe ok=5 fail=0` means the signing, proxy and
DB write path all work. Occasional `[401] retry in 5s with FRESH connection` lines are normal
(proxy egress pools carry a fixed share of throttled IPs; retries recover 96-100%).

## Phase 3 — Production Run

```cmd
:: foreground (simplest; stops if the console closes)
python batch_collect.py --full 27900

:: background via Task Scheduler (survives logoff/reboot; recommended for long runs)
schtasks /Create /TN "StarmakerCollect" /TR "<abs path to a .bat that runs the command above>" /SC ONCE /ST 23:59 /F
schtasks /Run /TN "StarmakerCollect"
```

- `--full N` collects the first N pending users and exits when done. Re-running the same command
  resumes: completed users are skipped, partially-collected users continue, inserts are deduplicated
  by the unique index — **interruptions are always safe**.
- Crash diagnostics go to `crash.log`; stdout goes to the redirect target (`collect_run.log`).

## Phase 4 — Monitoring

```cmd
.venv\Scripts\python progress_report.py
```

Reports creator status counts, per-user gaps, works volume, 401 rate, retry-recovery rate and
throughput. Healthy reference values from production:

| Metric | Expected |
|---|---|
| 401 rate | ~30-35% (shared proxy pool platform value) |
| retry recovery | 96-100% |
| throughput | ~15 requests/min, ~10 pages/min single instance |
| 429 rate | 0 |

## Phase 5 — Maintenance

| Task | Command |
|---|---|
| Reset interrupted users back to pending | `python reset_gap_users.py <uid> ...` |
| Reset all failed users | `python reset_gap_users.py --failed` |
| Full progress reset | `python reset_gap_users.py --all` |
| Inspect a gap (retry-exhausted vs inflated total) | `python diag_gaps.py <uid>` |
| Repair recording unique index | `python mongo_fix_index.py` |
| One-click health view | `python progress_report.py` |

Note: `collected_works < total_works` after a complete crawl is usually a server-side inflated
count (deleted/private works) and is unrecoverable — not an error.

## Phase 6 — Scaling

Single instance averages ~12 min/user. For 27,900 users that is months — plan accordingly:

1. **Dedicated static proxy** (root fix for the ~33% 401 tax; shared pools always carry dirty IPs)
2. **Multiple instances** — safe against each other: the unique index makes every insert idempotent,
   so parallel workers never duplicate data (only wasted overlapping requests if they pick the same
   pending users; stagger starts or shard the base table to avoid that)
3. Re-run `batch_collect.py --full N` periodically; it self-heals around interruptions

## How Dedup & Resume Work (the core design)

- Progress lives in `creator_ids.status` (0=pending, 1=done, 2=failed).
- Works live in `recording`, each doc keyed by the unique index `(owner_user_id, recording.sm_id)`.
- Every page insert is `insert_many(..., ordered=False)`; `BulkWriteError` code 11000 (duplicate)
  is swallowed, everything else is inserted. Hence: re-runs never duplicate, and a user is only
  marked done when its live document count reaches the server-reported total.
