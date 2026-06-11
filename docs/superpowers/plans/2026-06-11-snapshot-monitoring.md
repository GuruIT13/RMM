# Snapshot Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add silent random-interval screenshot monitoring — agent captures each monitor as separate PNGs to a write-only UNC share, with per-device/per-directory toggles and on-demand capture from the dashboard.

**Architecture:** Schema gains 4 columns on `directories` and 1 on `devices` for config/inheritance. Agent gets two new modules (`snapshot.py` captures screens, `snapshot_scheduler.py` runs the random-interval background thread) plus a new `take_snapshot` command handler. Dashboard gains a Snapshot Settings section in Directories and a per-device toggle + button in the device detail page.

**Tech Stack:** Python `mss` (screenshot), `pathlib.Path` (UNC write), Supabase PostgreSQL (config), Next.js App Router + Tailwind (dashboard UI), Supabase JS SDK (config reads/command dispatch).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `supabase/schema.sql` | Modify | Add migration SQL for new columns |
| `agent/requirements.txt` | Modify | Add `mss==9.0.2` |
| `agent/snapshot.py` | Create | Screenshot capture + sanitized UNC write |
| `agent/snapshot_scheduler.py` | Create | Random-interval background daemon thread |
| `agent/executor.py` | Modify | Add `take_snapshot` command handler |
| `agent/main.py` | Modify | Start snapshot_scheduler thread on startup |
| `dashboard/lib/types.ts` | Modify | Add snapshot fields to `Directory` and `Device` types |
| `dashboard/app/(dashboard)/directories/DirectoryManager.tsx` | Modify | Add Snapshot Settings section (super_admin only) |
| `dashboard/components/ActionButtons.tsx` | Modify | Add "Take Snapshot Now" button |
| `dashboard/app/(dashboard)/devices/[id]/page.tsx` | Modify | Fetch snapshot_enabled + pass to SnapshotToggle |
| `dashboard/components/SnapshotToggle.tsx` | Create | 3-state toggle (On/Off/Inherit) per device |

---

## Task 1: Database Migration

**Files:**
- Modify: `supabase/schema.sql`

- [ ] **Step 1: Add migration SQL to schema.sql**

Open `supabase/schema.sql` and append at the bottom (after all existing content):

```sql
-- ── Snapshot Monitoring (2026-06-11) ──────────────────────────────────────────
ALTER TABLE directories
  ADD COLUMN IF NOT EXISTS snapshot_enabled      boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS snapshot_share_path   text    DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS snapshot_min_interval integer DEFAULT 5,
  ADD COLUMN IF NOT EXISTS snapshot_max_interval integer DEFAULT 15;

ALTER TABLE devices
  ADD COLUMN IF NOT EXISTS snapshot_enabled boolean DEFAULT NULL;
```

- [ ] **Step 2: Run migration in Supabase SQL Editor**

Go to your Supabase project → SQL Editor, paste and run the SQL above.

Expected: no errors, `ALTER TABLE` success messages.

- [ ] **Step 3: Verify columns exist**

In Supabase SQL Editor run:
```sql
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name IN ('directories', 'devices')
  AND column_name LIKE 'snapshot%'
ORDER BY table_name, column_name;
```

Expected: 5 rows — 4 for `directories`, 1 for `devices`.

- [ ] **Step 4: Commit**

```bash
git add supabase/schema.sql
git commit -m "feat(db): add snapshot monitoring columns to directories and devices"
```

---

## Task 2: Agent — snapshot.py

**Files:**
- Modify: `agent/requirements.txt`
- Create: `agent/snapshot.py`

- [ ] **Step 1: Add mss to requirements**

In `agent/requirements.txt` add:
```
mss==9.0.2
```

- [ ] **Step 2: Install the dependency**

```bash
pip install mss==9.0.2
```

Expected: `Successfully installed mss-9.0.2`

- [ ] **Step 3: Create agent/snapshot.py**

```python
"""Screenshot capture — writes PNG files to a UNC network share."""
import logging
import re
import socket
from datetime import datetime
from pathlib import Path
from typing import Optional

import mss
import mss.tools

logger = logging.getLogger(__name__)

_FORBIDDEN = re.compile(r'[/\\:*?"<>|]')


def _safe_name(name: str) -> str:
    return _FORBIDDEN.sub("_", name).strip() or "device"


def take(
    share_path: str,
    display_name: Optional[str],
    hostname: Optional[str],
) -> list[str]:
    """
    Capture all monitors and write PNGs to share_path.
    Returns list of filenames written (basenames only).
    Falls back to hostname if display_name is None/empty.
    Returns [] on any failure — never raises.
    """
    prefix = _safe_name(display_name or hostname or socket.gethostname())
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = Path(share_path)

    written: list[str] = []
    try:
        with mss.mss() as sct:
            for i, monitor in enumerate(sct.monitors[1:], start=1):
                filename = f"{prefix}_{timestamp}_monitor{i}.png"
                filepath = dest / filename
                try:
                    img = sct.grab(monitor)
                    mss.tools.to_png(img.rgb, img.size, output=str(filepath))
                    written.append(filename)
                    logger.info("Snapshot saved: %s", filepath)
                except Exception as e:
                    logger.warning("Snapshot monitor %d failed: %s", i, e)
    except Exception as e:
        logger.warning("Snapshot share inaccessible (%s): %s", share_path, e)

    return written
```

- [ ] **Step 4: Verify import works**

```bash
cd agent
python -c "import snapshot; print('OK')"
```

Expected: `OK` (no ImportError)

- [ ] **Step 5: Commit**

```bash
git add agent/requirements.txt agent/snapshot.py
git commit -m "feat(agent): add snapshot.py — per-monitor PNG capture to UNC share"
```

---

## Task 3: Agent — snapshot_scheduler.py

**Files:**
- Create: `agent/snapshot_scheduler.py`

- [ ] **Step 1: Create agent/snapshot_scheduler.py**

```python
"""Background daemon thread — fetches config every interval and takes snapshots."""
import logging
import random
import threading
import time
from typing import Optional

from supabase import Client

import snapshot

logger = logging.getLogger(__name__)

_DEFAULT_MIN = 5   # minutes
_DEFAULT_MAX = 15  # minutes


def _fetch_config(supabase: Client, device_id: str) -> dict:
    """
    Returns merged config dict with keys:
      enabled: bool
      share_path: str | None
      min_interval: int (minutes)
      max_interval: int (minutes)
      display_name: str | None
      hostname: str | None
    Directory-level snapshot_enabled=false overrides device-level true.
    """
    try:
        res = supabase.table("devices").select(
            "snapshot_enabled, display_name, hostname, "
            "directories(snapshot_enabled, snapshot_share_path, snapshot_min_interval, snapshot_max_interval)"
        ).eq("id", device_id).single().execute()
        row = res.data or {}
        dir_cfg = row.get("directories") or {}

        dir_enabled = dir_cfg.get("snapshot_enabled") or False
        dev_enabled = row.get("snapshot_enabled")  # True | False | None

        if not dir_enabled:
            enabled = False
        elif dev_enabled is None:
            enabled = dir_enabled
        else:
            enabled = bool(dev_enabled)

        return {
            "enabled": enabled,
            "share_path": dir_cfg.get("snapshot_share_path"),
            "min_interval": dir_cfg.get("snapshot_min_interval") or _DEFAULT_MIN,
            "max_interval": dir_cfg.get("snapshot_max_interval") or _DEFAULT_MAX,
            "display_name": row.get("display_name"),
            "hostname": row.get("hostname"),
        }
    except Exception as e:
        logger.warning("snapshot_scheduler: config fetch failed: %s", e)
        return {
            "enabled": False,
            "share_path": None,
            "min_interval": _DEFAULT_MIN,
            "max_interval": _DEFAULT_MAX,
            "display_name": None,
            "hostname": None,
        }


def _scheduler_loop(supabase: Client, device_id: str) -> None:
    logger.info("Snapshot scheduler started for device %s", device_id)
    while True:
        cfg = _fetch_config(supabase, device_id)
        min_s = max(1, cfg["min_interval"]) * 60
        max_s = max(min_s, cfg["max_interval"] * 60)
        sleep_s = random.uniform(min_s, max_s)

        if cfg["enabled"] and cfg["share_path"]:
            try:
                written = snapshot.take(
                    share_path=cfg["share_path"],
                    display_name=cfg["display_name"],
                    hostname=cfg["hostname"],
                )
                if written:
                    logger.info("Snapshot: wrote %d file(s)", len(written))
            except Exception as e:
                logger.warning("Snapshot failed unexpectedly: %s", e)
        else:
            logger.debug("Snapshot disabled or no share path — skipping")

        time.sleep(sleep_s)


def start(supabase: Client, device_id: str) -> None:
    """Start the snapshot scheduler as a background daemon thread."""
    t = threading.Thread(
        target=_scheduler_loop,
        args=(supabase, device_id),
        daemon=True,
        name="snapshot-scheduler",
    )
    t.start()
    logger.info("Snapshot scheduler thread started")
```

- [ ] **Step 2: Verify import works**

```bash
cd agent
python -c "import snapshot_scheduler; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agent/snapshot_scheduler.py
git commit -m "feat(agent): add snapshot_scheduler — random-interval background thread"
```

---

## Task 4: Agent — executor.py + main.py

**Files:**
- Modify: `agent/executor.py` (add `take_snapshot` handler + dispatch entry)
- Modify: `agent/main.py` (start snapshot_scheduler thread)

- [ ] **Step 1: Add take_snapshot handler to executor.py**

In `agent/executor.py`, add the import at the top (after the existing imports):

```python
import snapshot as _snapshot
```

Then add this function before the `COMMAND_HANDLERS` dict:

```python
def handle_take_snapshot(supabase: Client, device_id: str) -> str:
    try:
        res = supabase.table("devices").select(
            "display_name, hostname, "
            "directories(snapshot_share_path)"
        ).eq("id", device_id).single().execute()
        row = res.data or {}
        share_path = (row.get("directories") or {}).get("snapshot_share_path")
        if not share_path:
            return "ERROR: No snapshot_share_path configured for this directory"
        written = _snapshot.take(
            share_path=share_path,
            display_name=row.get("display_name"),
            hostname=row.get("hostname"),
        )
        if not written:
            return "ERROR: No screenshots captured (share inaccessible or no monitors?)"
        return f"Captured {len(written)} file(s): {', '.join(written)}"
    except Exception as e:
        return f"ERROR: {e}"
```

- [ ] **Step 2: Add take_snapshot to COMMAND_HANDLERS**

In `agent/executor.py`, in the `COMMAND_HANDLERS` dict, add after `"uninstall_software"`:

```python
    "take_snapshot":            None,  # handled separately (needs supabase + device_id)
```

- [ ] **Step 3: Add take_snapshot dispatch in execute_command**

In `agent/executor.py`, in the `execute_command` function, add a branch for `take_snapshot` alongside the `get_anydesk_id` branch:

```python
        if cmd_type == "get_anydesk_id":
            output = handle_get_anydesk_id(supabase, device_id)
        elif cmd_type == "take_snapshot":
            output = handle_take_snapshot(supabase, device_id)
        elif cmd_type in COMMAND_HANDLERS and COMMAND_HANDLERS[cmd_type]:
```

- [ ] **Step 4: Add snapshot_scheduler start to main.py**

In `agent/main.py`, add the import:

```python
import snapshot_scheduler
```

In `main_async()`, after `start_tray(supabase_sync, device_id)`, add:

```python
    snapshot_scheduler.start(supabase_sync, device_id)
```

- [ ] **Step 5: Verify syntax**

```bash
cd agent
python -c "import executor; import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add agent/executor.py agent/main.py
git commit -m "feat(agent): add take_snapshot command + start snapshot_scheduler on boot"
```

---

## Task 5: Dashboard — TypeScript types

**Files:**
- Modify: `dashboard/lib/types.ts`

- [ ] **Step 1: Update Directory interface**

In `dashboard/lib/types.ts`, replace the `Directory` interface:

```typescript
export interface Directory {
  id: string;
  name: string;
  created_at: string;
  snapshot_enabled: boolean;
  snapshot_share_path: string | null;
  snapshot_min_interval: number;
  snapshot_max_interval: number;
}
```

- [ ] **Step 2: Update Device interface**

In `dashboard/lib/types.ts`, add `snapshot_enabled` to the `Device` interface after `is_approved`:

```typescript
  is_approved: boolean;
  snapshot_enabled: boolean | null;
  last_seen: string;
```

- [ ] **Step 3: Type-check**

```bash
cd dashboard
npx tsc --noEmit
```

Expected: no errors (or only pre-existing errors unrelated to snapshot fields)

- [ ] **Step 4: Commit**

```bash
git add dashboard/lib/types.ts
git commit -m "feat(dashboard): add snapshot fields to Directory and Device types"
```

---

## Task 6: Dashboard — SnapshotToggle component

**Files:**
- Create: `dashboard/components/SnapshotToggle.tsx`

- [ ] **Step 1: Create SnapshotToggle.tsx**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

type SnapshotState = true | false | null;

interface SnapshotToggleProps {
  deviceId: string;
  value: SnapshotState;
}

const OPTIONS: { value: SnapshotState; label: string }[] = [
  { value: true,  label: "On" },
  { value: null,  label: "Inherit" },
  { value: false, label: "Off" },
];

export default function SnapshotToggle({ deviceId, value }: SnapshotToggleProps) {
  const [current, setCurrent] = useState<SnapshotState>(value);
  const [saving, setSaving] = useState(false);
  const router = useRouter();

  const handleChange = async (next: SnapshotState) => {
    setSaving(true);
    const supabase = createClient();
    await supabase
      .from("devices")
      .update({ snapshot_enabled: next })
      .eq("id", deviceId);
    setCurrent(next);
    setSaving(false);
    router.refresh();
  };

  return (
    <div className="flex items-center gap-1">
      {OPTIONS.map((opt) => (
        <button
          key={String(opt.value)}
          disabled={saving}
          onClick={() => handleChange(opt.value)}
          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors disabled:opacity-50
            ${current === opt.value
              ? "bg-blue-600 text-white"
              : "bg-slate-700 text-slate-400 hover:bg-slate-600 hover:text-white"
            }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd dashboard
npx tsc --noEmit
```

Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/SnapshotToggle.tsx
git commit -m "feat(dashboard): add SnapshotToggle 3-state component (On/Off/Inherit)"
```

---

## Task 7: Dashboard — Device detail page (snapshot toggle + take button)

**Files:**
- Modify: `dashboard/app/(dashboard)/devices/[id]/page.tsx`
- Modify: `dashboard/components/ActionButtons.tsx`

- [ ] **Step 1: Fetch snapshot_enabled in device detail page**

In `dashboard/app/(dashboard)/devices/[id]/page.tsx`, update the `.select(...)` call to include `snapshot_enabled`:

```typescript
  const { data } = await supabase
    .from("devices")
    .select("id, directory_id, serial_number, hostname, display_name, os_info, cpu_name, cpu_usage, cpu_temp, ram_total, ram_usage, storage_total, storage_free, antivirus_status, firewall_status, anydesk_id, status, is_approved, snapshot_enabled, last_seen, created_at")
    .eq("id", id)
    .single();
```

- [ ] **Step 2: Add SnapshotToggle import and render in device detail page**

Add the import at the top of `dashboard/app/(dashboard)/devices/[id]/page.tsx`:

```typescript
import SnapshotToggle from "@/components/SnapshotToggle";
```

After the `<DeviceCard>` component in the JSX, add:

```tsx
      <div className="mt-6 bg-slate-800 rounded-xl border border-slate-700 px-4 py-4">
        <p className="text-xs text-slate-400 uppercase tracking-wide mb-3">Snapshot Monitoring</p>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-300">เครื่องนี้</span>
          <SnapshotToggle deviceId={device.id} value={device.snapshot_enabled} />
        </div>
        <p className="text-xs text-slate-500 mt-2">
          Inherit = ใช้ค่าของ Directory | On/Off = override เฉพาะเครื่องนี้
        </p>
      </div>
```

- [ ] **Step 3: Add "Take Snapshot Now" button to ActionButtons.tsx**

In `dashboard/components/ActionButtons.tsx`, add `take_snapshot` to `SIMPLE_ACTIONS`:

```typescript
  { type: "take_snapshot", label: "Take Snapshot", group: "action" },
```

Place it in the `action` group, after `"lock_screen"`.

- [ ] **Step 4: Type-check**

```bash
cd dashboard
npx tsc --noEmit
```

Expected: no new errors

- [ ] **Step 5: Commit**

```bash
git add dashboard/app/(dashboard)/devices/[id]/page.tsx dashboard/components/ActionButtons.tsx
git commit -m "feat(dashboard): add snapshot toggle + Take Snapshot button to device detail"
```

---

## Task 8: Dashboard — Directory snapshot settings

**Files:**
- Modify: `dashboard/app/(dashboard)/directories/page.tsx`
- Modify: `dashboard/app/(dashboard)/directories/DirectoryManager.tsx`

- [ ] **Step 1: Update directory page query to fetch snapshot columns**

In `dashboard/app/(dashboard)/directories/page.tsx`, update the select query:

```typescript
  const { data } = await supabase
    .from("directories")
    .select("id, name, created_at, snapshot_enabled, snapshot_share_path, snapshot_min_interval, snapshot_max_interval")
    .order("name");
```

- [ ] **Step 2: Add SnapshotSettings section to DirectoryManager.tsx**

Replace the full content of `dashboard/app/(dashboard)/directories/DirectoryManager.tsx` with:

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import type { Directory } from "@/lib/types";

interface SnapshotCfg {
  snapshot_enabled: boolean;
  snapshot_share_path: string;
  snapshot_min_interval: number;
  snapshot_max_interval: number;
}

function SnapshotSettings({ dir }: { dir: Directory }) {
  const [cfg, setCfg] = useState<SnapshotCfg>({
    snapshot_enabled: dir.snapshot_enabled,
    snapshot_share_path: dir.snapshot_share_path ?? "",
    snapshot_min_interval: dir.snapshot_min_interval,
    snapshot_max_interval: dir.snapshot_max_interval,
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    const supabase = createClient();
    const { error: err } = await supabase
      .from("directories")
      .update({
        snapshot_enabled: cfg.snapshot_enabled,
        snapshot_share_path: cfg.snapshot_share_path.trim() || null,
        snapshot_min_interval: cfg.snapshot_min_interval,
        snapshot_max_interval: cfg.snapshot_max_interval,
      })
      .eq("id", dir.id);
    if (err) setError(err.message);
    else { setSaved(true); setTimeout(() => setSaved(false), 2000); router.refresh(); }
    setSaving(false);
  };

  const inputCls = "bg-slate-700 text-white text-xs rounded px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-500 w-full";

  return (
    <div className="mt-3 border-t border-slate-700 pt-3 space-y-3">
      <p className="text-xs text-slate-400 uppercase tracking-wide">Snapshot Monitoring</p>

      {/* Enable toggle */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-slate-300 w-28">เปิด/ปิด Directory</span>
        <button
          onClick={() => setCfg((p) => ({ ...p, snapshot_enabled: !p.snapshot_enabled }))}
          className={`px-3 py-1 rounded text-xs font-medium transition-colors
            ${cfg.snapshot_enabled
              ? "bg-green-700/40 text-green-300 border border-green-600/40"
              : "bg-slate-700 text-slate-400 border border-slate-600"
            }`}
        >
          {cfg.snapshot_enabled ? "Enabled" : "Disabled"}
        </button>
      </div>

      {/* Share path */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-slate-300 w-28">Share Path</span>
        <input
          type="text"
          value={cfg.snapshot_share_path}
          onChange={(e) => setCfg((p) => ({ ...p, snapshot_share_path: e.target.value }))}
          placeholder={String.raw`\\192.168.1.10\Snapshot`}
          className={inputCls}
        />
      </div>

      {/* Intervals */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-slate-300 w-28">Interval (min)</span>
        <input
          type="number" min={1} max={60}
          value={cfg.snapshot_min_interval}
          onChange={(e) => setCfg((p) => ({ ...p, snapshot_min_interval: Number(e.target.value) }))}
          className="bg-slate-700 text-white text-xs rounded px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-500 w-20"
        />
        <span className="text-xs text-slate-500">to</span>
        <input
          type="number" min={1} max={120}
          value={cfg.snapshot_max_interval}
          onChange={(e) => setCfg((p) => ({ ...p, snapshot_max_interval: Number(e.target.value) }))}
          className="bg-slate-700 text-white text-xs rounded px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-500 w-20"
        />
        <span className="text-xs text-slate-500">นาที (random)</span>
      </div>

      {error && <p className="text-red-400 text-xs">{error}</p>}

      <button
        onClick={handleSave}
        disabled={saving}
        className={`px-4 py-1.5 rounded text-xs font-medium transition-colors disabled:opacity-50
          ${saved ? "bg-green-700 text-white" : "bg-blue-600 hover:bg-blue-500 text-white"}`}
      >
        {saving ? "..." : saved ? "Saved ✓" : "Save Snapshot Settings"}
      </button>
    </div>
  );
}

export default function DirectoryManager({ directories }: { directories: Directory[] }) {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedSnapshot, setExpandedSnapshot] = useState<string | null>(null);
  const router = useRouter();

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    const supabase = createClient();
    const { error: err } = await supabase.from("directories").insert({ name: name.trim() });
    if (err) setError(err.message);
    else { setName(""); router.refresh(); }
    setLoading(false);
  };

  const handleDelete = async (id: string, dirName: string) => {
    if (!confirm(`ลบ "${dirName}"? เครื่องที่อยู่ใน Directory นี้จะกลายเป็น NULL`)) return;
    const supabase = createClient();
    await supabase.from("directories").delete().eq("id", id);
    router.refresh();
  };

  return (
    <div className="space-y-4 max-w-lg">
      {/* Create form */}
      <form onSubmit={handleCreate} className="flex gap-2">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="ชื่อบริษัท/สาขา"
          className="flex-1 bg-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <button
          type="submit"
          disabled={loading || !name.trim()}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          {loading ? "..." : "+ สร้าง"}
        </button>
      </form>
      {error && <p className="text-red-400 text-xs">{error}</p>}

      {/* List */}
      <div className="space-y-2">
        {directories.map((dir) => (
          <div key={dir.id} className="bg-slate-800 rounded-xl border border-slate-700 px-4 py-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-white font-medium">{dir.name}</p>
                <p className="text-xs text-slate-500">{dir.id}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setExpandedSnapshot((p) => p === dir.id ? null : dir.id)}
                  className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded hover:bg-slate-700 transition-colors"
                >
                  {dir.snapshot_enabled ? "📷 On" : "📷 Off"}
                </button>
                <button
                  onClick={() => handleDelete(dir.id, dir.name)}
                  className="text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-red-900/20 transition-colors"
                >
                  ลบ
                </button>
              </div>
            </div>
            {expandedSnapshot === dir.id && <SnapshotSettings dir={dir} />}
          </div>
        ))}
        {directories.length === 0 && (
          <p className="text-slate-500 text-sm">ยังไม่มี Directory</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Type-check**

```bash
cd dashboard
npx tsc --noEmit
```

Expected: no new errors

- [ ] **Step 4: Commit**

```bash
git add dashboard/app/(dashboard)/directories/page.tsx dashboard/app/(dashboard)/directories/DirectoryManager.tsx
git commit -m "feat(dashboard): add snapshot settings section to directory manager"
```

---

## Task 9: Smoke Test

- [ ] **Step 1: Start the dashboard dev server**

```bash
cd dashboard
npm run dev
```

- [ ] **Step 2: Test Directory snapshot settings**

1. Go to `/directories`
2. Click the "📷 Off" button on any directory
3. Set share path to `\\127.0.0.1\test` (can be fake for UI test), enable toggle, set intervals 1–2
4. Click "Save Snapshot Settings"
5. Expected: "Saved ✓" appears, no errors

- [ ] **Step 3: Test per-device snapshot toggle**

1. Go to any approved device detail page
2. Verify "Snapshot Monitoring" section appears with On/Inherit/Off buttons
3. Click "On", verify button highlights blue
4. Click "Inherit", verify it switches back
5. Expected: no errors

- [ ] **Step 4: Test Take Snapshot button**

1. On device detail page, find "Take Snapshot" in Actions section
2. Click it
3. Expected: button shows "..." then green ring (command dispatched)

- [ ] **Step 5: Verify agent syntax**

```bash
cd agent
python -m py_compile snapshot.py snapshot_scheduler.py executor.py main.py
echo "All OK"
```

Expected: `All OK` (no SyntaxError)

- [ ] **Step 6: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: snapshot monitoring smoke test fixes"
```
