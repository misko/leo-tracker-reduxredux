from pathlib import Path
import os
code=Path('/tmp/three_track_train_only_candidate_search.py').read_text()
code=code.replace("exec(open('/tmp/compare_space_track_pipeline.py').read().replace(\"print(json.dumps(result,indent=2))\",''))", "exec(open('/tmp/three_track_cold_context.py').read())")
code=code.replace("'train_only_candidate_temporal_transfer.json'","'cold_candidate_temporal_transfer.json'")
if os.environ.get('THREE_TRACK_COLD_FOLD'):
    fold=os.environ['THREE_TRACK_COLD_FOLD'];assert fold in ['early_to_late','late_to_early']
    code=code.replace("splits=[('early_to_late',early),('late_to_early',~early)]",f"splits=[('{fold}',early)]" if fold=='early_to_late' else f"splits=[('{fold}',~early)]")
code=code.replace('original unseeded Space-Track position/calibration and candidate bank are frozen from the full scan','position, calibration, selected background bank, high-band contrast and initialization are learned by the cold pipeline from the declared training input; withheld target probe groups are absent from every pipeline stage')
exec(compile(code,__file__,'exec'))
