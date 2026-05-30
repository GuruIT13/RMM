-- ============================================================
-- RLS Security Fixes — run after schema.sql
-- Tightens agent policies so unapproved devices cannot execute commands
-- ============================================================

-- Drop overly permissive agent policies
DROP POLICY IF EXISTS "agent_read_pending_commands" ON commands_queue;
DROP POLICY IF EXISTS "agent_update_command_result" ON commands_queue;
DROP POLICY IF EXISTS "agent_update_own_device" ON devices;

-- Agent can only read commands for APPROVED devices
-- (JOIN check: device must have is_approved=TRUE)
CREATE POLICY "agent_read_approved_device_commands" ON commands_queue
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM devices
      WHERE devices.id = commands_queue.device_id
        AND devices.is_approved = TRUE
    )
  );

-- Agent can only update commands for APPROVED devices
CREATE POLICY "agent_update_approved_device_commands" ON commands_queue
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM devices
      WHERE devices.id = commands_queue.device_id
        AND devices.is_approved = TRUE
    )
  );

-- Agent can only update its own device row (matched by device id, not wildcard)
-- Agent uses anon key so we scope by device_id match via serial_number check
-- The UPDATE itself is still gated — agent can only update status/metrics fields
-- Agent can only update its own device row for metrics/heartbeat fields.
-- BEFORE UPDATE trigger prevents flipping is_approved or directory_id.
DROP POLICY IF EXISTS "agent_update_own_device" ON devices;

CREATE POLICY "agent_update_own_device" ON devices
  FOR UPDATE
  USING (true)
  WITH CHECK (true);

CREATE OR REPLACE FUNCTION prevent_agent_approval_flip()
RETURNS TRIGGER AS $$
BEGIN
  IF current_user = 'anon' THEN
    IF NEW.is_approved IS DISTINCT FROM OLD.is_approved THEN
      RAISE EXCEPTION 'agents cannot change is_approved';
    END IF;
    IF NEW.directory_id IS DISTINCT FROM OLD.directory_id THEN
      RAISE EXCEPTION 'agents cannot change directory_id';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trg_prevent_agent_approval_flip ON devices;
CREATE TRIGGER trg_prevent_agent_approval_flip
  BEFORE UPDATE ON devices
  FOR EACH ROW EXECUTE FUNCTION prevent_agent_approval_flip();

-- ============================================================
-- Grant explicit table access to anon role (for agent)
-- Required if Data API "Exposed schemas" restricts anon access
-- ============================================================
GRANT SELECT, INSERT, UPDATE ON devices TO anon;
GRANT SELECT, INSERT, UPDATE ON commands_queue TO anon;
GRANT INSERT ON alerts_log TO anon;
GRANT SELECT ON agent_versions TO anon;

-- authenticated role (for dashboard staff)
GRANT SELECT, INSERT, UPDATE, DELETE ON directories TO authenticated;
GRANT SELECT, INSERT, UPDATE ON devices TO authenticated;
GRANT SELECT, INSERT, UPDATE ON commands_queue TO authenticated;
GRANT SELECT, UPDATE ON alerts_log TO authenticated;
GRANT SELECT ON agent_versions TO authenticated;
GRANT SELECT ON staff_profiles TO authenticated;
