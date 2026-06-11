# Snapshot Monitoring — Design Spec

**Date:** 2026-06-11  
**Status:** Approved

## Overview

Silent, random-interval screenshot monitoring for MSP staff oversight. Agent captures each monitor as a separate PNG and writes directly to a write-only UNC network share. Admin can toggle per-device, per-directory, or trigger on-demand from the dashboard. Employees are not notified.

---

## 1. Schema Changes

### `directories` table — new columns

```sql
snapshot_enabled        boolean  DEFAULT false
snapshot_share_path     text     DEFAULT NULL   -- UNC path e.g. \\192.168.30.18\Snapshot
snapshot_min_interval   integer  DEFAULT 5      -- minutes
snapshot_max_interval   integer  DEFAULT 15     -- minutes
```

### `devices` table — new column

```sql
snapshot_enabled        boolean  DEFAULT NULL   -- NULL = inherit from directory
```

**Inheritance logic:**
- `devices.snapshot_enabled = true` → enabled (device override)
- `devices.snapshot_enabled = false` → disabled (device override)
- `devices.snapshot_enabled = NULL` → inherit `directories.snapshot_enabled`
- If `directories.snapshot_enabled = false` → all devices in directory stop, regardless of device override

`snapshot_share_path`, `snapshot_min_interval`, `snapshot_max_interval` always inherit from the directory (no per-device override).

---

## 2. Agent

### New file: `agent/snapshot.py`

Responsibilities:
- Capture each monitor as a separate PNG using the `mss` library
- Write directly to UNC path via `pathlib.Path` (Windows handles UNC natively)
- Filename format: `{display_name}_{YYYY-MM-DD}_{HHmmss}_monitor{N}.png`
  - Example: `PC-Accounting01_2026-06-11_143022_monitor1.png`
  - If `display_name` is not set (device not yet approved), fall back to `hostname`
  - Sanitize `display_name` — strip characters forbidden in Windows filenames: `/ \ : * ? " < > |`
- On inaccessible share: log warning, skip — do not crash agent
- On disconnected monitor during capture: skip that monitor, log warning

### New file: `agent/snapshot_scheduler.py`

Responsibilities:
- Background daemon thread, independent of Realtime listener
- Loop:
  1. Sleep `random(min_interval, max_interval)` minutes
  2. Re-fetch latest config from Supabase (`devices` JOIN `directories`)
  3. Evaluate inheritance logic
  4. If enabled and share path set → call `snapshot.take()`
- Re-fetches config every iteration — picks up config changes without agent restart

### `agent/executor.py` — new command

| command_type | Action |
|---|---|
| `take_snapshot` | Trigger one immediate snapshot (all monitors), return filenames written |

### `agent/requirements.txt` — new dependency

```
mss
```

---

## 3. Dashboard

### Directory Settings page — new section: "Snapshot Monitoring"

- Toggle: enable/disable for entire directory (super_admin only)
- Input: Share Path (`\\server\share`) — super_admin only, not visible to helpdesk
- Input: Min interval (minutes)
- Input: Max interval (minutes)

### Device List / Device Detail — per-device controls

- 3-state toggle: **On / Off / Inherit**
- Button: "Take Snapshot Now" → inserts `take_snapshot` into `commands_queue`
- Display: last snapshot time (from `executed_at` of most recent `take_snapshot` command)

### Access control

- `snapshot_share_path` visible/editable by `super_admin` only
- Toggle and "Take Snapshot Now" available to both `super_admin` and `helpdesk`

---

## 4. Security

- Agent runs as Windows Service (SYSTEM account) — UNC share must allow write access for `SYSTEM` or the machine's computer account (`DOMAIN\PC-NAME$`)
- Write-only share recommended: agents write, no one reads via the share path directly
- `display_name` sanitized before use as filename
- Share path not exposed to helpdesk role in dashboard

---

## 5. Edge Cases

| Scenario | Behavior |
|---|---|
| Share path NULL or empty | Scheduler skips, logs warning |
| Share inaccessible (network down) | Logs warning, skips interval |
| Monitor disconnected mid-capture | Skips that monitor, logs warning |
| Device not yet approved (no display_name) | Uses `hostname` as filename prefix |
| Agent offline during scheduled interval | Skips, resumes on next interval after reconnect |
| Directory disabled, device override ON | Directory wins — device does not capture |

---

## 6. File Summary

| File | Change |
|---|---|
| `supabase/schema.sql` | Add 4 columns to `directories`, 1 column to `devices` |
| `agent/snapshot.py` | New — screenshot capture + UNC write |
| `agent/snapshot_scheduler.py` | New — random interval background thread |
| `agent/executor.py` | Add `take_snapshot` handler |
| `agent/requirements.txt` | Add `mss` |
| `agent/main.py` | Start snapshot_scheduler thread on startup |
| `dashboard/` | Directory settings UI + per-device toggle + on-demand button |
