# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Enterprise OpenRMM (MSP Edition)

Two-component system:
- **Agent** — Python Windows Service running on client machines. Collects hardware metrics, registers itself with Supabase, listens for commands via Supabase Realtime, executes them silently, returns output.
- **Dashboard** — Next.js web app for IT Helpdesk. Shows device status grouped by Directory (company/branch), approves new devices, sends commands via Supabase Realtime.

## Tech Stack

| Layer | Technology |
|---|---|
| Database / Auth / Realtime | Supabase (PostgreSQL + Supabase Auth + Realtime + Edge Functions) |
| Agent | Python 3.10+: `supabase-py`, `psutil`, `wmi`, `pywin32`, `pystray` |
| Agent packaging | PyInstaller → `.exe`, NSSM for Windows Service |
| Dashboard | Next.js (App Router), TypeScript strict, Tailwind CSS, Supabase JS SDK |

## Supabase Project

- **URL:** `https://dnecmrpjcydmpreofmnl.supabase.co`
- **Schema:** `supabase/schema.sql` — deployed ✓ (2026-05-18)
- **Tables deployed:** `directories`, `staff_profiles`, `devices`, `commands_queue`, `alerts_log`, `agent_versions`
- **Realtime enabled on:** `devices`, `commands_queue`
- **RLS:** enabled on all tables, policies in `supabase/schema.sql`
- **Helper functions:** `is_staff()`, `is_super_admin()` (SECURITY DEFINER)

## Development Commands

> No build system initialized yet. Add commands here as each component is scaffolded.

**Agent:**
```
# Install deps
pip install -r agent/requirements.txt

# Run agent directly (dev mode, not as service)
python agent/main.py

# Build exe
pyinstaller agent/build.spec

# Install as Windows Service via NSSM
nssm install RMMAgent "C:\path\to\rmm_agent.exe"
nssm start RMMAgent

# Uninstall service
nssm remove RMMAgent confirm
```

**Dashboard (once scaffolded):**
```
cd dashboard
npm install
npm run dev        # dev server
npm run build      # production build
npm run lint       # ESLint
npx tsc --noEmit   # type-check only
```

## Database Schema

Six tables in Supabase PostgreSQL. RLS is **mandatory** on all tables.

| Table | Key columns | Notes |
|---|---|---|
| `directories` | `id`, `name` | Companies/branches |
| `staff_profiles` | `id` (→ `auth.users`), `role` (`super_admin`\|`helpdesk`) | IT staff accounts |
| `devices` | `id`, `directory_id`, `serial_number`, `hostname`, `status` (`online`\|`offline`), `is_approved` | `directory_id=NULL` + `is_approved=FALSE` = Unassigned |
| `commands_queue` | `device_id`, `command_type`, `payload` (JSONB), `status` (`pending`→`executing`→`completed`\|`failed`), `output_result` | Realtime-enabled |
| `alerts_log` | `device_id`, `severity` (`warning`\|`critical`), `is_resolved` | |
| `agent_versions` | `version_number`, `download_url` | Auto-update source |

Realtime is enabled on `commands_queue` and `devices`.

## Phase Status

| Phase | Status | Notes |
|---|---|---|
| Phase 1 — DB Schema | ✅ Done | `supabase/schema.sql` deployed 2026-05-18 |
| Phase 2 — Python Agent | ✅ Done | `agent/` — all modules written, not yet tested on real machine |
| Phase 3 — Realtime | ✅ Included in Phase 2 | `agent/realtime.py` |
| Phase 4 — Next.js Dashboard | ✅ Done | `dashboard/` — type check pass, dev server ขึ้น 2026-05-18 |
| Phase 5 — Enterprise UI | ✅ Done | Directories page, Kill Process UI, Realtime status dot, RLS patch 2026-05-18 |

## Architecture & Key Workflows

### Device Registration (Unassigned flow)
1. Agent starts → checks `serial_number` in `devices`
2. Not found → INSERT with `directory_id=NULL`, `is_approved=FALSE`
3. Dashboard admin goes to "Unassigned Devices" → sets `display_name`, `directory_id`, flips `is_approved=TRUE`
4. Device now visible in its Directory dashboard and able to receive commands

### Real-time Command Execution
1. Dashboard INSERTs row into `commands_queue` (`status='pending'`)
2. Agent receives Realtime event, sets `status='executing'`
3. Agent runs command via `subprocess.Popen` (hidden window, 300s timeout)
4. Agent UPDATEs `output_result` + `status='completed'` (or `'failed'`)
5. Dashboard receives Realtime update, displays result

### Supported `command_type` values
| Type | Action |
|---|---|
| `get_anydesk_id` | Run AnyDesk.exe --get-id, store in `devices.anydesk_id` |
| `disk_cleanup` | `cleanmgr.exe /sagerun:1` |
| `windows_update` | PowerShell PSWindowsUpdate |
| `kill_process` | `taskkill /F /IM <payload.process_name>` |
| `reboot` / `shutdown` | `shutdown /r /t 0 /f` or `/s` |
| `custom_cmd` | Arbitrary string, return stdout/stderr (5-min timeout) |

## Engineering Standards

These rules apply to all code written in this repo.

### Python (Agent)
- Type hints on every function signature
- `logging` with `RotatingFileHandler` only — no `print()`
- `subprocess`: always set `startupinfo` to hide windows, always set `timeout=300`, avoid `shell=True`
- WMI/hardware calls must catch exceptions and return `None`/default — never crash the main loop
- Supabase Realtime listener and monitoring loop must not block each other (use threads or asyncio correctly)

### TypeScript / Next.js (Dashboard)
- Strict mode — no `any` without explicit justification
- Every command dispatch must show Loading / Success / Error state in UI
- Tailwind only — no inline styles, no CSS modules
- Fetch only needed columns from Supabase (don't pull `output_result` in device list queries)

### Supabase / Security
- Every table needs RLS policies — write them alongside table creation SQL
- `Service Role Key` only in Edge Functions or server-side API routes — **never** in Agent or browser client
- Agent must check `is_approved=TRUE` before executing any command — reject unapproved devices at the database level via RLS, not only in app code
- No command injection: validate/sanitize `command_type` against the known enum, never interpolate raw user strings into shell commands
