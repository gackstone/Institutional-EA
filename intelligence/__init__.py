"""
Root level package alias for src.intelligence.
"""

import sys
from pathlib import Path

# Ensure src is accessible
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intelligence import *
