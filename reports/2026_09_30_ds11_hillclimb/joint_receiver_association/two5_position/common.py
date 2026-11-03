from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
ROOT = PARENT.parents[2]
sys.path.insert(0, str(PARENT))
sys.path.insert(0, str(ROOT))
from doppler_pilot import read, digest, fast

JOBS = [('original', 15, 0), ('original', 30, 0), ('additional', 11, 0), ('original', 24, 1), ('original', 31, 1), ('additional', 9, 1)]


def base(cohort):
    return PARENT.parent.parent / '2026_09_30_ds11_single10' if cohort == 'original' else PARENT.parent / 'additional'


def verify_sources(doc):
    for p, h in doc['sources'].items():
        assert digest(p) == h, p


def bindings(paths):
    return {str(p): digest(p) for p in paths}
