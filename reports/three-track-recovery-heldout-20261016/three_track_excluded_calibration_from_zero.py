from pathlib import Path
code=Path('/tmp/three_track_excluded_calibration_fit.py').read_text()
code=code.replace("for arm in ['fitted-c','zero-c']:","for arm in ['fitted-c']:")
code=code.replace('initial_nuisance=n.copy()',"""zero=json.loads((root/'excluded_calibration_zero-c.json').read_text())
assert zero['audit']['accepted']
start=np.array(zero['fit']['vector']);initial_nuisance=np.array(zero['fit']['nuisance'])""")
code=code.replace("'excluded_calibration_checkpoint_'+arm+'.json'","'excluded_calibration_checkpoint_'+arm+'_from_zero.json'")
code=code.replace("'excluded_calibration_'+arm+'.json'","'excluded_calibration_'+arm+'_from_zero.json'")
code=code.replace("qualification='129 target measurements", "initialization='Accepted zero-c target-excluded endpoint; optimization diagnostic, not matched model budget comparison',qualification='129 target measurements")
exec(compile(code,__file__,'exec'))
