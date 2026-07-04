import os
import tempfile

# Must be set before any app module is imported (settings are cached):
# serial in-process scanning makes test scans deterministic and debuggable.
os.environ.setdefault("SCAN_WORKERS", "0")
os.environ.setdefault("SCAN_BATCH_SIZE", "50")
# Startup recovery would touch the dev database from inside TestClient lifespans.
os.environ.setdefault("RECOVER_SCANS_ON_STARTUP", "0")
# Thumbnails must never land in the real cache during tests.
os.environ.setdefault("THUMBNAIL_CACHE_DIR", tempfile.mkdtemp(prefix="aperture-test-thumbs-"))
