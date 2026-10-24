"""Record reproducible DS24 inference sources separately from membership."""
import sys,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(REPO/'tools'))
from run_algo02_ds23 import source_closure
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
entries=['tools/algo02_scan.py','tools/prepare_algo02_ds23.py',
         'tools/probe_ds23_family_cavity_nominations.py','tools/probe_ds23_family_cavity_position.py',
         'tools/probe_ds23_graph_seeded_paths.py','tools/probe_ds23_iteration010_path_feasibility.py']
sources=source_closure(entries)
local={str(p.relative_to(OUT)):sha(p) for folder in ['engine','contrast'] for p in (OUT/folder).glob('*.py')}
record=dict(dataset='DS24',created_utc=datetime.now(timezone.utc).isoformat(),
    manifest_sha256=sha(OUT/'manifest.json'),sample_sha256=sha(OUT/'sample.json'),
    scope='Fresh ALGO02 + qualified causal signed phase prior + equal-prior family-cavity reference; DS23 graph reentry bank not reused',
    methods=['algo02_historical','baseline','native_full','native_full_matched','native_fixed','native_contrasts'],
    region_center=[37.906,-122.545],box_width_km=25,arms=['c0','fitted_c'],
    candidate_selection_c_arm='c0 with paired qualification',
    native_shared_paths_and_aliases=True,calibration_from_curved_only=True,
    native_matched_start='baseline parent',native_phase_rounds=5,native_iterations=48,
    original_native_control='existing cold fit and near-feasible rescue',
    GPS_for_reporting_only=True,post_observation_TLE=False,new_RF=False,
    fixed_evaluation_membership=True,all_failures_retained=True,
    source_sha256=sources,local_source_sha256=local,
    preparation_caps_s=[180,600],algo02_cap_s=900,cavity_cap_s=960,variant_supervisor_cap_s=1200)
path=OUT/'study_protocol.json'
if path.exists():raise FileExistsError('preserve protocol')
path.write_text(json.dumps(record,indent=2)+'\n')
