"""Shared panel and coordinate conventions for the ten independent pilot implementations."""
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
FROZEN = Path("/home/mouse9911/.cache/accuracy-repair-20261115/frozen-001/src")
for path in (FROZEN, ROOT/"support", ROOT/"support/stream", ROOT/"support/frontend"):
    if str(path) not in sys.path:
        sys.path.insert(0,str(path))
PANEL = json.loads((ROOT/"panel.json").read_text())
CASES = PANEL["cases"]


def latlon(xy):
    lat, lon = PANEL["search_center_latlon"]
    return [lat + float(xy[1])/111., lon + float(xy[0])/(111.32*math.cos(math.radians(lat)))]
