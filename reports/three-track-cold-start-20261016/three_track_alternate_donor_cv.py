from pathlib import Path
import os
code=Path('/tmp/three_track_cold_candidate_cv.py').read_text()
code=code.replace("exec(open('/tmp/three_track_cold_context.py').read())","exec(open('/tmp/three_track_alternate_donor_context.py').read())")
code=code.replace('cold_candidate_temporal_transfer.json','alternate_B_'+os.environ['THREE_TRACK_ALTERNATE_DONOR']+'_temporal_transfer.json')
exec(compile(code,__file__,'exec'))
