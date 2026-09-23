"""Reuse the published scan-1aa numerical pipeline on the frozen rate cohort."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
runner = ROOT.parent/'2026_09_23_scan_1aa_phase_methods/replay_methods.py'
spec = importlib.util.spec_from_file_location('phase_method_replay', runner)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
for entry in json.loads((ROOT/'selection.json').read_text()):
    if entry['session_id'] == 'scan-fw-1aa1d50103d97388':
        continue  # Exact existing replay is the anchor, not a new selection.
    module.OUT = ROOT/entry['session_id']
    module.run()
