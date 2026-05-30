-- Per-directory staff access control
-- super_admin: sees everything (unchanged)
-- helpdesk: sees only directories in their access list

CREATE TABLE IF NOT EXISTS staff_directory_access (
  staff_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  directory_id UUID REFERENCES directories(id) ON DELETE CASCADE NOT NULL,
  granted_by   UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  PRIMARY KEY (staff_id, directory_id)
);

CREATE INDEX IF NOT EXISTS idx_sda_staff_id ON staff_directory_access (staff_id);
CREATE INDEX IF NOT EXISTS idx_sda_directory_id ON staff_directory_access (directory_id);

ALTER TABLE staff_directory_access ENABLE ROW LEVEL SECURITY;

CREATE POLICY "admin_manage_staff_access" ON staff_directory_access FOR ALL USING (is_super_admin());
CREATE POLICY "staff_read_own_access" ON staff_directory_access FOR SELECT
  USING (staff_id = auth.uid());

CREATE OR REPLACE FUNCTION can_access_directory(dir_id UUID)
RETURNS BOOLEAN AS $$
  SELECT
    is_super_admin()
    OR EXISTS (
      SELECT 1 FROM staff_directory_access
      WHERE staff_id = auth.uid() AND directory_id = dir_id
    );
$$ LANGUAGE sql SECURITY DEFINER;

-- Devices with directory_id IS NULL are unassigned — only super_admin can see them.
-- can_access_directory(NULL) always returns false for helpdesk (SQL NULL semantics).
-- This is intentional: unassigned devices are managed exclusively by super_admin.
DROP POLICY IF EXISTS "staff_read_approved_devices" ON devices;
CREATE POLICY "staff_read_approved_devices" ON devices
  FOR SELECT
  USING (
    is_staff() AND (
      (directory_id IS NULL AND is_super_admin())
      OR can_access_directory(directory_id)
    )
  );

DROP POLICY IF EXISTS "staff_read_directories" ON directories;
CREATE POLICY "staff_read_directories" ON directories
  FOR SELECT
  USING (
    is_super_admin()
    OR EXISTS (
      SELECT 1 FROM staff_directory_access
      WHERE staff_id = auth.uid() AND directory_id = directories.id
    )
  );

DROP POLICY IF EXISTS "staff_read_commands" ON commands_queue;
DROP POLICY IF EXISTS "staff_send_commands" ON commands_queue;
CREATE POLICY "staff_read_commands" ON commands_queue
  FOR SELECT
  USING (
    is_staff() AND EXISTS (
      SELECT 1 FROM devices
      WHERE devices.id = commands_queue.device_id
        AND can_access_directory(devices.directory_id)
    )
  );
CREATE POLICY "staff_send_commands" ON commands_queue
  FOR INSERT
  WITH CHECK (
    is_staff() AND EXISTS (
      SELECT 1 FROM devices
      WHERE devices.id = commands_queue.device_id
        AND can_access_directory(devices.directory_id)
    )
  );

DROP POLICY IF EXISTS "staff_read_alerts" ON alerts_log;
CREATE POLICY "staff_read_alerts" ON alerts_log
  FOR SELECT
  USING (
    is_staff() AND EXISTS (
      SELECT 1 FROM devices
      WHERE devices.id = alerts_log.device_id
        AND can_access_directory(devices.directory_id)
    )
  );
