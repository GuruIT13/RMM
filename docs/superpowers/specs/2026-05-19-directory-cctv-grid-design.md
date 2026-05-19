# Design: Directory Sidebar + CCTV Device Grid

**Date:** 2026-05-19  
**Status:** Approved

## Problem

Current dashboard (`app/(dashboard)/page.tsx`) shows all directories stacked in one long scroll — no collapse, no sidebar navigation. Device cards are rows, not a visual grid. No per-device refresh button.

## Goal

1. Sidebar directory navigation — click a directory to view its devices
2. CCTV-style device grid — compact cards showing live status and metrics
3. Per-device ↻ refresh (re-fetch that device's row from Supabase DB)
4. Directory-level ↻ Refresh All
5. Click card → navigate to `/devices/[id]` (existing detail page with tabs)

## Layout

```
┌────┬──────────────┬─────────────────────────────────────┐
│    │ DIRECTORIES  │  บริษัท ABC จำกัด  ● 4/6  [↻ All][⊞☰]│
│nav │              │─────────────────────────────────────│
│    │ ▶ ABC จำกัด  │  [PC-001 card] [PC-002 card] [...]  │
│    │   XYZ Co.    │  [PC-003 card] [PC-004 card] [...]  │
│    │   สาขาเหนือ  │                                     │
│    │              │                                     │
└────┴──────────────┴─────────────────────────────────────┘
56px    180px              flex-1
```

## Components

### 1. `DirectorySidebar` (new client component)
- Props: `directories: Directory[]` with online/total counts
- State: `selectedId: string` (synced with URL query param `?dir=`)
- Renders directory list — active highlighted in purple, shows `● N / total`
- Search input filters directory list client-side

### 2. `DeviceGrid` (new client component)
- Props: `directoryId: string`
- Fetches devices for selected directory via Supabase client on mount + on `directoryId` change
- State: `devices: Device[]`, `refreshing: Set<string>` (per-device), `refreshingAll: boolean`
- Renders 3-column responsive grid (2 on tablet, 1 on mobile)
- Refresh All button re-fetches all rows in directory

### 3. `DeviceCCTVCard` (new client component)
- Props: `device: Device`, `onRefresh: () => Promise<void>`, `refreshing: boolean`
- Shows: status dot (glowing green = online, gray = offline), display_name/hostname, OS info
- Metric panels: CPU% (blue), RAM% (purple), Free disk (green) — warn color if threshold exceeded
- AnyDesk badge if present
- ↻ button (stops propagation, calls onRefresh)
- Card click → `router.push('/devices/' + device.id)`
- Offline cards: reduced opacity, shows "Last seen X ago" instead of metrics

### 4. `/devices/[id]` page (new — or repurpose existing DeviceCard expand logic)
- Full detail page for one device
- Contains existing tabs: Commands / Software / Processes / Hardware
- Back button → returns to dashboard with directory preserved (`?dir=...`)

### 5. `app/(dashboard)/page.tsx` (refactor)
- Becomes a thin shell: renders `DirectorySidebar` + `DeviceGrid` side by side
- Server-fetches directories (with online count via join or separate query)
- Passes initial directory list to sidebar; device fetching moves to `DeviceGrid`

## Data Flow

```
page.tsx (server)
  └─ fetch directories + online counts → pass to DirectorySidebar

DirectorySidebar (client)
  └─ user clicks directory → updates ?dir= URL param

DeviceGrid (client)
  └─ reads ?dir= → fetches devices for that directory
  └─ ↻ All → re-fetch all
  └─ passes onRefresh per device to DeviceCCTVCard

DeviceCCTVCard (client)
  └─ ↻ → re-fetch single device row (SELECT * FROM devices WHERE id=?)
  └─ click → router.push('/devices/[id]')
```

## Refresh Behavior

- **Per-device ↻**: `supabase.from('devices').select(...).eq('id', device.id).single()` → update that card in state
- **Refresh All**: re-fetch all devices in directory → replace state
- No command sent to agent — reads current DB values only
- Realtime subscription on `devices` table optional (can add later)

## Thresholds for Warning Colors

| Metric | Warn | Critical |
|--------|------|----------|
| CPU% | > 80% | > 95% |
| RAM% | > 85% | > 95% |
| Free disk | < 10 GB | < 5 GB |

## Files to Create/Modify

| File | Action |
|------|--------|
| `app/(dashboard)/page.tsx` | Refactor — thin shell, server-fetch directories |
| `components/DirectorySidebar.tsx` | New |
| `components/DeviceGrid.tsx` | New |
| `components/DeviceCCTVCard.tsx` | New |
| `app/(dashboard)/devices/[id]/page.tsx` | New — device detail page |
| `lib/types.ts` | Possibly add `DirectoryWithCount` type |

## Icons

Use **Lucide React** (`lucide-react`) instead of emoji throughout — install as first step.

| Location | Icon |
|----------|------|
| Nav — Dashboard | `LayoutGrid` |
| Nav — Alerts | `Bell` |
| Nav — Staff | `Users` |
| Nav — Unassigned | `Inbox` |
| Nav — Directories | `Building2` |
| Directory sidebar item | `FolderOpen` / `Folder` |
| Online dot | `Circle` (filled green, CSS glow) |
| Offline dot | `Circle` (filled gray) |
| Refresh button | `RefreshCw` |
| Card → detail | `ChevronRight` |
| Search | `Search` |
| Grid toggle | `LayoutGrid` / `List` |

**Install:** `npm install lucide-react` (add to dependencies in package.json)

## Out of Scope

- Realtime auto-update of metrics (agent heartbeat updates DB; manual refresh only for now)
- List view toggle (build grid only; toggle UI can be placeholder)
- Drag-and-drop or reorder

## Verification

1. `npm run dev` — no TypeScript errors
2. Navigate to dashboard → sidebar shows all directories with counts
3. Click directory → grid loads devices for that directory only
4. ↻ on a card → spinner shows, metrics update
5. ↻ Refresh All → all cards update
6. Click card → navigates to `/devices/[id]` with full tabs
7. Back button → returns to dashboard with same directory selected
