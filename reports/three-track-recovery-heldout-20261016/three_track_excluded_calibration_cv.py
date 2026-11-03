import sys
from pathlib import Path
arm=sys.argv[1]
assert arm in ['fitted-c','zero-c','fitted-c_from_zero']
code=Path('/tmp/three_track_train_only_candidate_search.py').read_text()
injection=f'''
f=json.loads((root/'excluded_calibration_{arm}.json').read_text())
assert f['audit']['accepted']
v=np.array(f['fit']['vector']);n=np.array(f['fit']['nuisance'])
'''
code=code.replace('begun=time.monotonic()',injection+'\nbegun=time.monotonic()')
code=code.replace("'train_only_candidate_temporal_transfer.json'",f"'excluded_calibration_cv_{arm}.json'")
code=code.replace('original unseeded Space-Track position/calibration and candidate bank are frozen from the full scan','position/calibration are fitted with all 129 target measurements excluded; the candidate bank, frozen high-band contrast and saved warm start retain full-scan conditioning')
exec(compile(code,__file__,'exec'))
