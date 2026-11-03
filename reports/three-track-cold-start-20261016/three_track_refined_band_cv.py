from pathlib import Path
import os
code=Path('/tmp/three_track_cold_candidate_cv.py').read_text()
code=code.replace("exec(open('/tmp/three_track_cold_context.py').read())","exec(open('/tmp/three_track_refined_band_context.py').read())")
suffix='' if os.environ.get('THREE_TRACK_BAND_PASS','1')=='1' else '_pass2'
code=code.replace('cold_candidate_temporal_transfer.json','refine_band_contrast_'+os.environ['THREE_TRACK_BAND_VARIANT']+'_'+os.environ['THREE_TRACK_BAND_ARM']+suffix+'_temporal_transfer.json')
exec(compile(code,__file__,'exec'))
