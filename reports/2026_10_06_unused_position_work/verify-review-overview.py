import importlib.util, sys, tempfile, json
from pathlib import Path
spec=importlib.util.spec_from_file_location('candidate_review',sys.argv[1])
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix='leo-review-parity-') as directory:
    root=Path(directory)
    full=m.build_report('scan-fw-cc609ed603589e6e',root/'full',maximum_tracks=1)
    lean=m.build_report('scan-fw-cc609ed603589e6e',root/'lean',maximum_tracks=1,render_overview=False)
    assert (root/'full'/full['figure']).is_file()
    assert lean['figure'] is None
    assert not list((root/'lean').glob('*top5-polynomial-rms.png'))
    assert full['tracks']==lean['tracks']
    assert full['track_figures']==lean['track_figures']
    assert all((root/'full'/name).read_bytes()==(root/'lean'/name).read_bytes() for name in full['track_figures'])
    print(json.dumps({'session':full['session_id'],'track_count':len(full['tracks']), 'exact_track_data':True,'exact_published_pngs':True,'overview_omitted':True}))
