"""Inherited both-terminal public reporting, no import-time reference calls."""
import importlib.util
import sys
from pathlib import Path

def build(plan, directory, protocol_digest, **options):
    previous = Path(__file__).resolve().parent.parent/'2026_10_10_position_error_iter148'
    sys.path.insert(0, str(previous))
    spec = importlib.util.spec_from_file_location('report148_for150', previous/'report.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build(plan, directory, protocol_digest, **options)
