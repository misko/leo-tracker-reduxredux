from pathlib import Path
code=Path('/tmp/scoped_timing_refit.py').read_text()
code=code.replace("((observations.receiver==0)&(observations.channel<=4))", "(observations.channel<=4)")
code=code.replace("'scoped_timing_fit.json'", "'shared_band_timing_fit.json'").replace("'scoped_timing_result.json'", "'shared_band_timing_result.json'")
code=code.replace('fixed satellite/receiver/band timing-shaped correction','fixed satellite/band timing-shaped correction shared across both receivers')
exec(compile(code,__file__,'exec'))
