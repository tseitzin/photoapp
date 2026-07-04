import os

# Must be set before any app module is imported (settings are cached):
# serial in-process scanning makes test scans deterministic and debuggable.
os.environ.setdefault("SCAN_WORKERS", "0")
os.environ.setdefault("SCAN_BATCH_SIZE", "50")
# Startup recovery would touch the dev database from inside TestClient lifespans.
os.environ.setdefault("RECOVER_SCANS_ON_STARTUP", "0")
