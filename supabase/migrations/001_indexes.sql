-- Performance indexes for frequently queried columns
-- Run after schema.sql

-- devices: filter by directory + approval status (main dashboard query)
CREATE INDEX IF NOT EXISTS idx_devices_directory_id ON devices (directory_id);
CREATE INDEX IF NOT EXISTS idx_devices_directory_approved ON devices (directory_id, is_approved);
CREATE INDEX IF NOT EXISTS idx_devices_status ON devices (status);

-- commands_queue: filter by device, sort by date (fetchLastCommands query)
CREATE INDEX IF NOT EXISTS idx_commands_device_id ON commands_queue (device_id);
CREATE INDEX IF NOT EXISTS idx_commands_device_created ON commands_queue (device_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_commands_status ON commands_queue (status) WHERE status IN ('pending', 'executing');

-- alerts_log: filter unresolved by device (fetchAlerts query)
CREATE INDEX IF NOT EXISTS idx_alerts_device_id ON alerts_log (device_id);
CREATE INDEX IF NOT EXISTS idx_alerts_device_unresolved ON alerts_log (device_id, is_resolved) WHERE is_resolved = FALSE;

-- staff_profiles: role lookup (is_super_admin, is_staff helpers)
CREATE INDEX IF NOT EXISTS idx_staff_id_role ON staff_profiles (id, role);
