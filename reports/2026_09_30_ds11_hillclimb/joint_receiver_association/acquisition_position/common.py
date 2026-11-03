from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
ROOT = PARENT.parents[2]
sys.path.insert(0, str(PARENT))
sys.path.insert(0, str(ROOT))
from doppler_pilot import read, digest, fast

JOBS = [('original', 0, 2), ('original', 18, 3), ('original', 21, 4), ('original', 2, 5), ('original', 1, 6), ('original', 5, 7), ('additional', 1, 2), ('additional', 2, 3), ('additional', 0, 4), ('additional', 5, 6), ('additional', 3, 7)]


def base(cohort):
    return PARENT.parent.parent / '2026_09_30_ds11_single10' if cohort == 'original' else PARENT.parent / 'additional'


def verify_sources(doc):
    for p, h in doc['sources'].items():
        assert digest(p) == h, p


def bindings(paths):
    return {str(p): digest(p) for p in paths}
