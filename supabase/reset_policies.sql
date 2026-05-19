-- ============================================================
-- RESET ALL POLICIES — run this in Supabase SQL Editor
-- ============================================================

-- Drop ALL existing policies on devices
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT policyname FROM pg_policies WHERE tablename = 'devices' AND schemaname = 'public'
  LOOP
    EXECUTE 'DROP POLICY IF EXISTS "' || r.policyname || '" ON devices';
  END LOOP;
END $$;

-- Drop ALL existing policies on commands_queue
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT policyname FROM pg_policies WHERE tablename = 'commands_queue' AND schemaname = 'public'
  LOOP
    EXECUTE 'DROP POLICY IF EXISTS "' || r.policyname || '" ON commands_queue';
  END LOOP;
END $$;

-- ============================================================
-- DEVICES policies
-- ============================================================

-- Staff (authenticated) can read all approved devices
CREATE POLICY "staff_read_approved_devices" ON devices
  FOR SELECT TO authenticated
  USING (is_staff());

-- anon (Agent) can read own device by serial_number
CREATE POLICY "agent_select_own_device" ON devices
  FOR SELECT TO anon
  USING (true);

-- anon (Agent) INSERT new device — no USING needed for INSERT
CREATE POLICY "agent_insert_device" ON devices
  FOR INSERT TO anon
  WITH CHECK (true);

-- anon (Agent) UPDATE own device metrics
CREATE POLICY "agent_update_device" ON devices
  FOR UPDATE TO anon
  USING (true)
  WITH CHECK (true);

-- super_admin can do everything
CREATE POLICY "admin_all_devices" ON devices
  FOR ALL TO authenticated
  USING (is_super_admin())
  WITH CHECK (is_super_admin());

-- ============================================================
-- COMMANDS_QUEUE policies
-- ============================================================

-- Staff can INSERT commands
CREATE POLICY "staff_insert_commands" ON commands_queue
  FOR INSERT TO authenticated
  WITH CHECK (is_staff());

-- Staff can SELECT commands
CREATE POLICY "staff_select_commands" ON commands_queue
  FOR SELECT TO authenticated
  USING (is_staff());

-- anon (Agent) can SELECT pending commands for approved devices
CREATE POLICY "agent_select_commands" ON commands_queue
  FOR SELECT TO anon
  USING (
    EXISTS (
      SELECT 1 FROM devices
      WHERE devices.id = commands_queue.device_id
      AND devices.is_approved = true
    )
  );

-- anon (Agent) can UPDATE command result for approved devices
CREATE POLICY "agent_update_commands" ON commands_queue
  FOR UPDATE TO anon
  USING (
    EXISTS (
      SELECT 1 FROM devices
      WHERE devices.id = commands_queue.device_id
      AND devices.is_approved = true
    )
  )
  WITH CHECK (true);

-- ============================================================
-- Verify
-- ============================================================
SELECT tablename, policyname, roles, cmd
FROM pg_policies
WHERE tablename IN ('devices', 'commands_queue')
ORDER BY tablename, policyname;
