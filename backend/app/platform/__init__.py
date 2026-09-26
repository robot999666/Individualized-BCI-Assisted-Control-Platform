"""Personalized control platform: persistent metadata and explicitly simulated devices."""
import sys
from pathlib import Path

# Make the repository-owned integration package available from backend working dirs.
_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)
