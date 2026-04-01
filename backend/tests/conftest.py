import os
import sys
from pathlib import Path


# Ensure `import app...` works no matter where pytest is invoked from.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Optional: allow setting DATABASE_URL via env when running tests.
os.environ.setdefault("SESSION_SECRET", "dev-secret-change-me")

