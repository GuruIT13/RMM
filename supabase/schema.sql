-- ============================================================
-- Enterprise OpenRMM - Database Schema
-- Run this in Supabase Dashboard > SQL Editor
-- ============================================================

-- 1. Directories (บริษัท/สาขา)
CREATE TABLE directories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Staff Profiles (พนักงาน IT)
CREATE TABLE staff_profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('super_admin', 'helpdesk')),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Devices (เครื่องลูกค้า)
CREATE TABLE devices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  directory_id UUID REFERENCES directories(id) ON DELETE SET NULL,
  serial_number TEXT UNIQUE NOT NULL,
  hostname TEXT NOT NULL,
  display_name TEXT,
  os_info TEXT,
  cpu_name TEXT,
  cpu_usage FLOAT DEFAULT 0,
  cpu_temp FLOAT DEFAULT 0,
  ram_total BIGINT DEFAULT 0,
  ram_usage FLOAT DEFAULT 0,
  storage_total BIGINT DEFAULT 0,
  storage_free BIGINT DEFAULT 0,
  antivirus_status TEXT,
  firewall_status BOOLEAN,
  anydesk_id TEXT,
  status TEXT DEFAULT 'offline' CHECK (status IN ('online', 'offline')),
  is_approved BOOLEAN DEFAULT FALSE,
  last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Commands Queue (คิวคำสั่ง Real-time)
CREATE TABLE commands_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id UUID REFERENCES devices(id) ON DELETE CASCADE NOT NULL,
  requested_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  command_type TEXT NOT NULL,
  payload JSONB,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'executing', 'completed', 'failed')),
  output_result TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  executed_at TIMESTAMP WITH TIME ZONE
);

-- 5. Alerts Log
CREATE TABLE alerts_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id UUID REFERENCES devices(id) ON DELETE CASCADE NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('warning', 'critical')),
  message TEXT NOT NULL,
  is_resolved BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. Agent Versions (Auto-Update)
CREATE TABLE agent_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version_number TEXT UNIQUE NOT NULL,
  download_url TEXT NOT NULL,
  release_notes TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- Enable Realtime
-- ============================================================
ALTER PUBLICATION supabase_realtime ADD TABLE commands_queue;
ALTER PUBLICATION supabase_realtime ADD TABLE devices;

-- ============================================================
-- Row Level Security
-- ============================================================
ALTER TABLE directories ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE commands_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_versions ENABLE ROW LEVEL SECURITY;

-- Helper: check if caller is authenticated staff
CREATE OR REPLACE FUNCTION is_staff()
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM staff_profiles WHERE id = auth.uid()
  );
$$ LANGUAGE sql SECURITY DEFINER;

-- Helper: check if caller is super_admin
CREATE OR REPLACE FUNCTION is_super_admin()
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM staff_profiles WHERE id = auth.uid() AND role = 'super_admin'
  );
$$ LANGUAGE sql SECURITY DEFINER;

-- directories: staff can read, super_admin can write
CREATE POLICY "staff_read_directories" ON directories FOR SELECT USING (is_staff());
CREATE POLICY "admin_write_directories" ON directories FOR ALL USING (is_super_admin());

-- staff_profiles: staff can read own profile, super_admin can manage all
CREATE POLICY "staff_read_own_profile" ON staff_profiles FOR SELECT USING (id = auth.uid() OR is_super_admin());
CREATE POLICY "admin_manage_profiles" ON staff_profiles FOR ALL USING (is_super_admin());

-- devices: staff can read approved devices, agent (anon) can insert/update own device
CREATE POLICY "staff_read_approved_devices" ON devices FOR SELECT USING (is_staff());
CREATE POLICY "agent_register_device" ON devices FOR INSERT WITH CHECK (true); -- anon can self-register
CREATE POLICY "agent_update_own_device" ON devices FOR UPDATE USING (true);    -- agent updates by serial_number match
CREATE POLICY "admin_manage_devices" ON devices FOR ALL USING (is_super_admin());

-- commands_queue: staff can insert (send commands), agent (anon) can read pending + update result
CREATE POLICY "staff_send_commands" ON commands_queue FOR INSERT WITH CHECK (is_staff());
CREATE POLICY "staff_read_commands" ON commands_queue FOR SELECT USING (is_staff());
CREATE POLICY "agent_read_pending_commands" ON commands_queue FOR SELECT USING (true); -- agent reads by device_id
CREATE POLICY "agent_update_command_result" ON commands_queue FOR UPDATE USING (true); -- agent writes output_result

-- alerts_log: staff can read/resolve, agent can insert
CREATE POLICY "staff_read_alerts" ON alerts_log FOR SELECT USING (is_staff());
CREATE POLICY "staff_resolve_alerts" ON alerts_log FOR UPDATE USING (is_staff());
CREATE POLICY "agent_insert_alert" ON alerts_log FOR INSERT WITH CHECK (true);

-- agent_versions: anyone can read (agent checks for updates)
CREATE POLICY "public_read_agent_versions" ON agent_versions FOR SELECT USING (true);
CREATE POLICY "admin_manage_agent_versions" ON agent_versions FOR ALL USING (is_super_admin());

-- ── Snapshot Monitoring (2026-06-11) ──────────────────────────────────────────
ALTER TABLE directories
  ADD COLUMN IF NOT EXISTS snapshot_enabled      boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS snapshot_share_path   text    DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS snapshot_min_interval integer DEFAULT 5,
  ADD COLUMN IF NOT EXISTS snapshot_max_interval integer DEFAULT 15;

ALTER TABLE devices
  ADD COLUMN IF NOT EXISTS snapshot_enabled boolean DEFAULT NULL;
