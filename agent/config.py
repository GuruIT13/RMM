import os

SUPABASE_URL = "https://dnecmrpjcydmpreofmnl.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRuZWNtcnBqY3lkbXByZW9mbW5sIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkwNzE3NDgsImV4cCI6MjA5NDY0Nzc0OH0"
    ".2O9D7ld9fssX4LIYzwZ016Mx7iZBJtZ3COVZbwE4dA8"
)

AGENT_VERSION = "1.0.0"
HEARTBEAT_INTERVAL = 30   # seconds between metric updates
COMMAND_TIMEOUT = 300      # max seconds for any subprocess command
LOG_MAX_BYTES = 5_242_880  # 5 MB per log file
LOG_BACKUP_COUNT = 3
LOG_FILE = os.path.join(os.path.dirname(__file__), "rmm_agent.log")
