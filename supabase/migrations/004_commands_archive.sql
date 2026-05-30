-- commands_archive: cold storage for completed commands older than 30 days
-- Identical schema to commands_queue

CREATE TABLE IF NOT EXISTS commands_archive (
  LIKE commands_queue INCLUDING ALL
);

CREATE INDEX IF NOT EXISTS idx_archive_device_created ON commands_archive (device_id, created_at DESC);

ALTER TABLE commands_archive ENABLE ROW LEVEL SECURITY;
CREATE POLICY "staff_read_commands_archive" ON commands_archive FOR SELECT USING (is_staff());

CREATE OR REPLACE FUNCTION archive_old_commands()
RETURNS void AS $$
BEGIN
  INSERT INTO commands_archive
  SELECT * FROM commands_queue
  WHERE status IN ('completed', 'failed')
    AND created_at < NOW() - INTERVAL '30 days'
  ON CONFLICT (id) DO NOTHING;

  DELETE FROM commands_queue
  WHERE status IN ('completed', 'failed')
    AND created_at < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Schedule: run daily at 02:00 UTC (requires pg_cron extension)
SELECT cron.schedule(
  'archive-old-commands',
  '0 2 * * *',
  'SELECT archive_old_commands()'
);
