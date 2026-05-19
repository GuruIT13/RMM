# Directory Sidebar + CCTV Device Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current scroll-based dashboard with a sidebar directory navigator and CCTV-style device grid, with per-device and per-directory refresh buttons.

**Architecture:** Server component fetches directories with online counts and passes them to a client-side `DirectorySidebar`. Selecting a directory updates the `?dir=` URL param, which `DeviceGrid` reads to fetch and display devices. Each `DeviceCCTVCard` re-fetches its own row on ↻; clicking a card navigates to `/devices/[id]` for full detail. Existing `DeviceCard` expand logic moves to the new detail page.

**Tech Stack:** Next.js 16 App Router, TypeScript strict, Tailwind CSS, Supabase JS (client + server), lucide-react

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `dashboard/package.json` | Modify | Add lucide-react dependency |
| `dashboard/lib/types.ts` | Modify | Add `DirectoryWithCount` type |
| `dashboard/components/Sidebar.tsx` | Modify | Replace emoji icons with Lucide icons |
| `dashboard/components/DirectorySidebar.tsx` | Create | Directory list with search, online counts, active highlight |
| `dashboard/components/DeviceCCTVCard.tsx` | Create | Single device card — metrics, refresh, click to detail |
| `dashboard/components/DeviceGrid.tsx` | Create | Grid of cards for selected directory, refresh all |
| `dashboard/app/(dashboard)/page.tsx` | Modify | Thin server shell: fetch directories+counts, render sidebar+grid |
| `dashboard/app/(dashboard)/devices/[id]/page.tsx` | Create | Device detail page with existing tabs (Commands/Software/Processes/Hardware) |

---

## Task 1: Install lucide-react

**Files:**
- Modify: `dashboard/package.json`

- [ ] **Step 1: Install the package**

```bash
cd dashboard
npm install lucide-react
```

Expected output: `added N packages` with lucide-react in dependencies.

- [ ] **Step 2: Verify install**

```bash
node -e "require('lucide-react'); console.log('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add dashboard/package.json dashboard/package-lock.json
git commit -m "feat: add lucide-react for SVG icons"
```

---

## Task 2: Add `DirectoryWithCount` type

**Files:**
- Modify: `dashboard/lib/types.ts`

- [ ] **Step 1: Add type after the existing `Directory` interface**

Open `dashboard/lib/types.ts`. After line 10 (closing `}` of `Directory`), add:

```typescript
export interface DirectoryWithCount extends Directory {
  onlineCount: number;
  totalCount: number;
}
```

- [ ] **Step 2: Type-check**

```bash
cd dashboard
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/lib/types.ts
git commit -m "feat: add DirectoryWithCount type"
```

---

## Task 3: Replace emoji icons in Sidebar with Lucide

**Files:**
- Modify: `dashboard/components/Sidebar.tsx`

- [ ] **Step 1: Replace full file content**

```typescript
"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { LayoutGrid, Inbox, Bell, Building2, Users, LogOut } from "lucide-react";

const navItems = [
  { href: "/",            label: "Dashboard",    Icon: LayoutGrid },
  { href: "/unassigned",  label: "Unassigned",   Icon: Inbox },
  { href: "/alerts",      label: "Alerts",       Icon: Bell },
  { href: "/directories", label: "Directories",  Icon: Building2 },
  { href: "/staff",       label: "Manage Staff", Icon: Users },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = async () => {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  };

  return (
    <aside className="w-56 bg-slate-800 flex flex-col h-screen sticky top-0">
      <div className="px-5 py-6 border-b border-slate-700">
        <h1 className="text-lg font-bold text-white">OpenRMM</h1>
        <p className="text-xs text-slate-400 mt-0.5">MSP Edition</p>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ href, label, Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                active
                  ? "bg-blue-600 text-white"
                  : "text-slate-300 hover:bg-slate-700 hover:text-white"
              }`}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="px-3 py-4 border-t border-slate-700">
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
        >
          <LogOut size={16} />
          ออกจากระบบ
        </button>
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd dashboard
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/Sidebar.tsx
git commit -m "feat: replace emoji icons with Lucide icons in Sidebar"
```

---

## Task 4: Create `DirectorySidebar` component

**Files:**
- Create: `dashboard/components/DirectorySidebar.tsx`

- [ ] **Step 1: Create file**

```typescript
"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Folder, FolderOpen, Search } from "lucide-react";
import type { DirectoryWithCount } from "@/lib/types";

interface DirectorySidebarProps {
  directories: DirectoryWithCount[];
}

export default function DirectorySidebar({ directories }: DirectorySidebarProps) {
  const router = useRouter();
  const params = useSearchParams();
  const selectedId = params.get("dir") ?? directories[0]?.id ?? "";
  const [query, setQuery] = useState("");

  const filtered = directories.filter((d) =>
    d.name.toLowerCase().includes(query.toLowerCase())
  );

  const select = (id: string) => {
    const sp = new URLSearchParams(params.toString());
    sp.set("dir", id);
    router.push(`/?${sp.toString()}`);
  };

  return (
    <div className="w-44 bg-slate-900 border-r border-slate-700 flex flex-col h-full flex-shrink-0">
      <div className="px-3 py-3 border-b border-slate-700">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-2">
          Directories
        </p>
        <div className="flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5">
          <Search size={12} className="text-slate-500 flex-shrink-0" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="ค้นหา..."
            className="bg-transparent text-xs text-slate-300 placeholder-slate-600 outline-none w-full"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5">
        {filtered.map((dir) => {
          const active = dir.id === selectedId;
          const Icon = active ? FolderOpen : Folder;
          return (
            <button
              key={dir.id}
              onClick={() => select(dir.id)}
              className={`w-full flex items-start gap-2 px-2 py-2 rounded-lg text-left transition-colors ${
                active
                  ? "bg-violet-900/40 border border-violet-700/40 text-violet-200"
                  : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              }`}
            >
              <Icon size={13} className="flex-shrink-0 mt-0.5" />
              <div className="min-w-0">
                <p className="text-xs font-medium truncate leading-tight">{dir.name}</p>
                <p className="text-xs mt-0.5">
                  <span className={dir.onlineCount > 0 ? "text-green-400" : "text-slate-600"}>
                    ● {dir.onlineCount}
                  </span>
                  <span className="text-slate-600"> / {dir.totalCount}</span>
                </p>
              </div>
            </button>
          );
        })}

        {filtered.length === 0 && (
          <p className="text-xs text-slate-600 px-2 py-3">ไม่พบ</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd dashboard
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/DirectorySidebar.tsx
git commit -m "feat: add DirectorySidebar component"
```

---

## Task 5: Create `DeviceCCTVCard` component

**Files:**
- Create: `dashboard/components/DeviceCCTVCard.tsx`

- [ ] **Step 1: Create file**

```typescript
"use client";

import { useRouter } from "next/navigation";
import { RefreshCw, ChevronRight } from "lucide-react";
import type { Device } from "@/lib/types";

interface DeviceCCTVCardProps {
  device: Device;
  onRefresh: () => Promise<void>;
  refreshing: boolean;
}

function formatFree(bytes: number): string {
  if (!bytes) return "–";
  const gb = bytes / 1_073_741_824;
  return gb >= 1 ? `${gb.toFixed(0)}G` : `${(bytes / 1_048_576).toFixed(0)}M`;
}

function metricColor(value: number, warnAt: number, critAt: number, base: string): string {
  if (value >= critAt) return "text-red-400";
  if (value >= warnAt) return "text-amber-400";
  return base;
}

function freeColor(bytes: number): string {
  const gb = bytes / 1_073_741_824;
  if (gb < 5)  return "text-red-400";
  if (gb < 10) return "text-amber-400";
  return "text-emerald-400";
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60)  return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)   return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function DeviceCCTVCard({ device, onRefresh, refreshing }: DeviceCCTVCardProps) {
  const router = useRouter();
  const isOnline = device.status === "online";

  return (
    <div
      onClick={() => router.push(`/devices/${device.id}`)}
      className={`relative bg-slate-900 rounded-xl border cursor-pointer transition-all group
        ${isOnline
          ? "border-green-900/50 hover:border-green-700/60"
          : "border-slate-800 opacity-55 hover:opacity-70"
        }`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 pt-3 pb-2">
        <span
          className={`w-2 h-2 rounded-full flex-shrink-0 transition-colors ${
            isOnline ? "bg-green-400 shadow-[0_0_6px_#4ade80]" : "bg-slate-600"
          }`}
        />
        <p className="flex-1 text-xs font-semibold text-slate-100 truncate">
          {device.display_name ?? device.hostname}
        </p>
        <button
          onClick={(e) => { e.stopPropagation(); onRefresh(); }}
          disabled={refreshing}
          className="text-slate-600 hover:text-slate-300 transition-colors disabled:opacity-40"
          title="Refresh"
        >
          <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} />
        </button>
      </div>

      {/* OS info */}
      <p className="px-3 pb-2 text-xs text-slate-500 truncate">{device.os_info ?? "–"}</p>

      {/* Metrics or offline message */}
      {isOnline ? (
        <div className="px-3 pb-3 grid grid-cols-3 gap-1.5">
          <div className="bg-slate-800/60 rounded-md p-1.5 text-center">
            <p className={`text-xs font-bold leading-none ${metricColor(device.cpu_usage, 80, 95, "text-blue-400")}`}>
              {device.cpu_usage?.toFixed(0) ?? "–"}%
            </p>
            <p className="text-[9px] text-slate-600 mt-0.5">CPU</p>
          </div>
          <div className="bg-slate-800/60 rounded-md p-1.5 text-center">
            <p className={`text-xs font-bold leading-none ${metricColor(device.ram_usage, 85, 95, "text-violet-400")}`}>
              {device.ram_usage?.toFixed(0) ?? "–"}%
            </p>
            <p className="text-[9px] text-slate-600 mt-0.5">RAM</p>
          </div>
          <div className="bg-slate-800/60 rounded-md p-1.5 text-center">
            <p className={`text-xs font-bold leading-none ${freeColor(device.storage_free)}`}>
              {formatFree(device.storage_free)}
            </p>
            <p className="text-[9px] text-slate-600 mt-0.5">FREE</p>
          </div>
        </div>
      ) : (
        <p className="px-3 pb-3 text-xs text-slate-600 text-center">
          Last seen {timeAgo(device.last_seen)}
        </p>
      )}

      {/* Footer: AnyDesk + arrow */}
      <div className="px-3 pb-2.5 flex items-center gap-2">
        {device.anydesk_id ? (
          <span className="text-[9px] bg-blue-900/30 text-blue-400 border border-blue-800/30 rounded px-1.5 py-0.5 truncate max-w-[80px]">
            {device.anydesk_id}
          </span>
        ) : (
          <span className="text-[9px] text-slate-700">No AnyDesk</span>
        )}
        <ChevronRight size={11} className="ml-auto text-slate-700 group-hover:text-slate-400 transition-colors" />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd dashboard
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/DeviceCCTVCard.tsx
git commit -m "feat: add DeviceCCTVCard component"
```

---

## Task 6: Create `DeviceGrid` component

**Files:**
- Create: `dashboard/components/DeviceGrid.tsx`

- [ ] **Step 1: Create file**

```typescript
"use client";

import { useEffect, useState, useCallback } from "react";
import { RefreshCw } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import type { Device } from "@/lib/types";
import DeviceCCTVCard from "./DeviceCCTVCard";

const DEVICE_COLUMNS = "id, directory_id, serial_number, hostname, display_name, os_info, cpu_name, cpu_usage, cpu_temp, ram_total, ram_usage, storage_total, storage_free, antivirus_status, firewall_status, anydesk_id, status, is_approved, last_seen";

interface DeviceGridProps {
  directoryId: string;
  directoryName: string;
}

export default function DeviceGrid({ directoryId, directoryName }: DeviceGridProps) {
  const [devices, setDevices]           = useState<Device[]>([]);
  const [loading, setLoading]           = useState(true);
  const [refreshingAll, setRefreshingAll] = useState(false);
  const [refreshing, setRefreshing]     = useState<Set<string>>(new Set());

  const fetchAll = useCallback(async () => {
    const supabase = createClient();
    const { data } = await supabase
      .from("devices")
      .select(DEVICE_COLUMNS)
      .eq("directory_id", directoryId)
      .eq("is_approved", true)
      .order("status", { ascending: false })
      .order("hostname");
    setDevices((data as Device[]) ?? []);
  }, [directoryId]);

  useEffect(() => {
    setLoading(true);
    fetchAll().finally(() => setLoading(false));
  }, [fetchAll]);

  const handleRefreshAll = async () => {
    setRefreshingAll(true);
    await fetchAll();
    setRefreshingAll(false);
  };

  const handleRefreshOne = async (deviceId: string) => {
    setRefreshing((prev) => new Set(prev).add(deviceId));
    const supabase = createClient();
    const { data } = await supabase
      .from("devices")
      .select(DEVICE_COLUMNS)
      .eq("id", deviceId)
      .single();
    if (data) {
      setDevices((prev) =>
        prev.map((d) => (d.id === deviceId ? (data as Device) : d))
      );
    }
    setRefreshing((prev) => {
      const next = new Set(prev);
      next.delete(deviceId);
      return next;
    });
  };

  const onlineCount = devices.filter((d) => d.status === "online").length;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-800 flex-shrink-0">
        <div>
          <h2 className="text-sm font-bold text-slate-100">{directoryName}</h2>
          <p className="text-xs text-slate-500">
            <span className={onlineCount > 0 ? "text-green-400" : "text-slate-600"}>
              ● {onlineCount} online
            </span>
            {" · "}
            {devices.length - onlineCount} offline
            {" · "}
            {devices.length} total
          </p>
        </div>
        <button
          onClick={handleRefreshAll}
          disabled={refreshingAll || loading}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-xs bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-40"
        >
          <RefreshCw size={12} className={refreshingAll ? "animate-spin" : ""} />
          Refresh All
        </button>
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <RefreshCw size={20} className="text-slate-600 animate-spin" />
          </div>
        ) : devices.length === 0 ? (
          <p className="text-slate-600 text-sm text-center py-12">ไม่มีเครื่องใน directory นี้</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {devices.map((device) => (
              <DeviceCCTVCard
                key={device.id}
                device={device}
                onRefresh={() => handleRefreshOne(device.id)}
                refreshing={refreshing.has(device.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd dashboard
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/components/DeviceGrid.tsx
git commit -m "feat: add DeviceGrid component with per-device refresh"
```

---

## Task 7: Refactor `app/(dashboard)/page.tsx` — thin server shell

**Files:**
- Modify: `dashboard/app/(dashboard)/page.tsx`

- [ ] **Step 1: Replace full file content**

```typescript
import { createClient } from "@/lib/supabase/server";
import type { DirectoryWithCount } from "@/lib/types";
import DirectorySidebar from "@/components/DirectorySidebar";
import DeviceGrid from "@/components/DeviceGrid";

export const revalidate = 0;

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ dir?: string }>;
}) {
  const supabase = await createClient();
  const sp = await searchParams;

  // Fetch directories
  const { data: directories } = await supabase
    .from("directories")
    .select("id, name, created_at")
    .order("name");

  const dirList = directories ?? [];

  // Fetch approved device counts per directory in one query
  const { data: counts } = await supabase
    .from("devices")
    .select("directory_id, status")
    .eq("is_approved", true)
    .not("directory_id", "is", null);

  const countMap = new Map<string, { online: number; total: number }>();
  for (const row of counts ?? []) {
    const id = row.directory_id as string;
    const entry = countMap.get(id) ?? { online: 0, total: 0 };
    entry.total += 1;
    if (row.status === "online") entry.online += 1;
    countMap.set(id, entry);
  }

  const directoriesWithCount: DirectoryWithCount[] = dirList.map((d) => ({
    ...d,
    onlineCount: countMap.get(d.id)?.online ?? 0,
    totalCount: countMap.get(d.id)?.total ?? 0,
  }));

  const selectedId = sp.dir ?? directoriesWithCount[0]?.id ?? "";
  const selectedDir = directoriesWithCount.find((d) => d.id === selectedId);

  return (
    <div className="flex h-full">
      <DirectorySidebar directories={directoriesWithCount} />
      {selectedDir ? (
        <DeviceGrid
          directoryId={selectedDir.id}
          directoryName={selectedDir.name}
        />
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-slate-600 text-sm">ยังไม่มี Directory — สร้างที่เมนู Directories</p>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd dashboard
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Update dashboard layout to use full height**

Open `dashboard/app/(dashboard)/layout.tsx`. Change `<main className="flex-1 overflow-auto">` to:

```typescript
<main className="flex-1 overflow-hidden">{children}</main>
```

This lets the inner grid scroll instead of the whole page.

- [ ] **Step 4: Type-check again**

```bash
cd dashboard
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/app/(dashboard)/page.tsx dashboard/app/(dashboard)/layout.tsx
git commit -m "feat: refactor dashboard page to sidebar + CCTV grid layout"
```

---

## Task 8: Create `/devices/[id]` detail page

**Files:**
- Create: `dashboard/app/(dashboard)/devices/[id]/page.tsx`

This page moves the existing expanded `DeviceCard` content (tabs) into a dedicated route.

- [ ] **Step 1: Create the file**

```typescript
import { notFound } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import type { Device } from "@/lib/types";
import DeviceCard from "@/components/DeviceCard";
import { ChevronLeft } from "lucide-react";

export const revalidate = 0;

export default async function DeviceDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ dir?: string }>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const supabase = await createClient();

  const { data } = await supabase
    .from("devices")
    .select("id, directory_id, serial_number, hostname, display_name, os_info, cpu_name, cpu_usage, cpu_temp, ram_total, ram_usage, storage_total, storage_free, antivirus_status, firewall_status, anydesk_id, status, is_approved, last_seen, created_at")
    .eq("id", id)
    .single();

  if (!data) notFound();

  const device = data as Device;
  const backHref = sp.dir ? `/?dir=${sp.dir}` : "/";

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <Link
        href={backHref}
        className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white mb-6 transition-colors"
      >
        <ChevronLeft size={16} />
        กลับ Dashboard
      </Link>

      <DeviceCard device={device} defaultExpanded />
    </div>
  );
}
```

- [ ] **Step 2: Add `defaultExpanded` prop to `DeviceCard`**

Open `dashboard/components/DeviceCard.tsx`. Find:

```typescript
export default function DeviceCard({ device }: DeviceCardProps) {
  const [expanded, setExpanded] = useState(false);
```

Change to:

```typescript
interface DeviceCardProps { device: Device; defaultExpanded?: boolean; }

export default function DeviceCard({ device, defaultExpanded = false }: DeviceCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
```

- [ ] **Step 3: Type-check**

```bash
cd dashboard
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add dashboard/app/(dashboard)/devices/[id]/page.tsx dashboard/components/DeviceCard.tsx
git commit -m "feat: add device detail page at /devices/[id]"
```

---

## Task 9: Manual end-to-end verification

- [ ] **Step 1: Start dev server**

```bash
cd dashboard
npm run dev
```

Expected: server starts on `http://localhost:3000`, no errors in terminal.

- [ ] **Step 2: Verify sidebar**

Open `http://localhost:3000`. Confirm:
- Left sidebar shows Lucide icons (no emoji)
- Directory sidebar shows directory names with `● N / total` counts
- Search input filters directory list

- [ ] **Step 3: Verify grid**

Click a directory. Confirm:
- Header shows directory name + online/offline counts
- CCTV cards appear in grid
- Online devices: glowing green dot + CPU/RAM/FREE metrics
- Offline devices: gray dot + "Last seen Xh ago"

- [ ] **Step 4: Verify per-device refresh**

Click ↻ on a card. Confirm:
- Icon spins while refreshing
- Card updates with fresh data from DB

- [ ] **Step 5: Verify Refresh All**

Click "Refresh All" button. Confirm:
- Button spins
- All cards refresh

- [ ] **Step 6: Verify card navigation**

Click a device card. Confirm:
- Navigates to `/devices/[id]`
- Page shows DeviceCard in expanded state with all 4 tabs
- "กลับ Dashboard" link returns to correct directory

- [ ] **Step 7: Final type-check + lint**

```bash
cd dashboard
npx tsc --noEmit && npm run lint
```

Expected: no errors.
