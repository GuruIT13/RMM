-- Add SHA-256 checksum field to agent_versions for secure auto-update verification
ALTER TABLE agent_versions
  ADD COLUMN IF NOT EXISTS checksum_sha256 TEXT;

COMMENT ON COLUMN agent_versions.checksum_sha256 IS 'Hex-encoded SHA-256 hash of the .exe download. Agent must verify before executing.';
