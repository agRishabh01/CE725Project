"""Root conftest. Ensures backend/ is on sys.path so `from api...` imports work in tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
