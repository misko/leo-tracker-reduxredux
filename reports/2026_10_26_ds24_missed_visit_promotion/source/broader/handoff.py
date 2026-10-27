"""Audit acquired native owners and emit component public graph inputs."""
import argparse
import os
import shutil
import signal
from pathlib import Path
import sys
import time
import application as app

HERE=app.HERE;REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')

def main(case):
    began=time.monotonic()
    assert all(os.environ.get(k)=='1' for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'])
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120second graph handoff bound')))
    signal.alarm(120)
    p=app.read(app.RAW/'protocol.json')
    for path,h in p['files'].items():assert app.sha(path)==h,path
    assert case in p['cases']
    graph_protocol=app.read(HERE/'graph_protocol.json')
    for path,h in graph_protocol['files'].items():assert app.sha(path)==h,path
    sys.path.insert(0,str(app.R01/'validation'))
    from baseline_scope import metadata_inventory
    from prepare_overlay import rebuild_graph
    from integration import bank_reuse_audit,digest,graph_inputs_changed
    integrate=app.module('frozen_coherent_graph_integration',app.R01/'validation/coherent_application/integrate.py')
    import replay
    math,adapter=replay.engine().frozen_modules()
    reuse={r['case']:r for r in app.read(HERE/'reuse_audit.json')['cases']}
    if case in reuse:
        r=reuse[case];outcome=Path(r['outcome_path']);integrate.TIMING=Path(r['selection_root'])
        assert app.sha(outcome)==r['outcome_sha256']
        upstream=r['upstream_protocol_sha256']
    elif case in p['no_eligible_cases']:
        outcome=None;doc=dict(rows=[]);integrate.TIMING=app.RAW;upstream=app.sha(app.RAW/'protocol.json')
    else:
        outcome=app.RAW/'outcomes'/(case+'.json.gz');integrate.TIMING=app.RAW;upstream=app.sha(app.RAW/'protocol.json')
        assert app.read(app.RAW/'terminal'/(case+'.json'))['exit_code']==0
    if outcome:
        doc=app.read(outcome);assert doc['protocol_sha256']==upstream
    slots=app.read(HERE/'panel.json')['slots']
    forecasts={r['header']['prediction_id']:r for r in app.read(HERE/'prediction_packets_v2.json')['rows'] if r['header']['case']==case}
    ledger=integrate.integrate_case(case,doc,slots,forecasts,math,adapter)
    ledger['raw_outcome_sha256']=app.sha(outcome) if outcome else None
    ledger['protocol_sha256']=upstream
    ledger_path=HERE/'ledgers'/(case+'_additions.json');app.write(ledger_path,ledger)
    original=app.read(app.SOURCE/case/'observations.json');old_tracks=app.read(app.SOURCE/case/'tracks.json')
    rows=ledger['observations'];assert rows[:len(original)]==original
    assert len({o['observation_id'] for o in rows})==len(rows)
    new={r['target_observation_id'] for r in ledger['staged']}
    assert new=={o['observation_id'] for o in rows}-{o['observation_id'] for o in original}
    folder=HERE/'graphs'/case;folder.mkdir(parents=True,exist_ok=False)
    if new:
        config=app.read(REPO/'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json')['config']
        tracks,g=rebuild_graph(rows,case,config)
        app.write(folder/'observations.json',rows);app.write(folder/'tracks.json',tracks)
    else:
        tracks=old_tracks;g={}
        for name in ['observations.json','tracks.json']:shutil.copyfile(app.SOURCE/case/name,folder/name)
    import numpy as np
    with np.load(app.SOURCE/case/'bank.npz') as bank:
        support=bank_reuse_audit(bank['time_s'].tolist(),bank['norad'].tolist(),
            app.read(app.SOURCE/case/'nominal_elements.json'),app.read(app.SOURCE/'causal_prior'/case/'receipt.json'),old_tracks,tracks)
    assert support['reuse_allowed'],support
    graph_ids={oid for t in tracks for oid in t['observation_ids']}
    curved=set(g.get('curved_observation_ids',[]))
    audit=dict(case=case,status='complete',method='exact_R01_coherent_only',
        no_eligible_lane=case in p['no_eligible_cases'],new_native_owners=len(new),new_in_graph=len(new&graph_ids),
        new_in_curved_graph=len(new&curved),new_outside_graph=len(new-graph_ids),
        new_native_ids=sorted(new),new_curved_ids=sorted(new&curved),graph=g,
        original_GLRT_count=len(original),total_GLRT_count=len(rows),original_observation_prefix_exact=True,
        original_measurements_and_margins_exact=True,unique_native_owners=True,
        baseline_equivalent_inputs=not new,bank_support=support,
        input_changes=graph_inputs_changed(original,rows,old_tracks,tracks),
        observations_digest=digest(rows),tracks_digest=digest(tracks),
        observations_sha256=app.sha(folder/'observations.json'),tracks_sha256=app.sha(folder/'tracks.json'),
        ledger_path=str(ledger_path),ledger_sha256=app.sha(ledger_path),
        raw_outcome_path=str(outcome) if outcome else None,raw_outcome_sha256=app.sha(outcome) if outcome else None,
        raw_protocol_sha256=upstream,application_protocol_sha256=app.sha(app.RAW/'protocol.json'),
        graph_protocol_sha256=app.sha(HERE/'graph_protocol.json'),source_input_protocol_sha256=app.sha(HERE/'forecast_protocol.json'),
        no_sparse_union=True,no_recovered_donors=True,geographic_inputs=False,forced_satellite_identity=False,
        seconds=time.monotonic()-began)
    app.write(folder/'new_native_owners.json',dict(case=case,observation_ids=sorted(new),ledger_sha256=app.sha(ledger_path)))
    app.write(folder/'audit.json',audit)
    seal={str(q):app.sha(q) for q in [folder/'observations.json',folder/'tracks.json',folder/'new_native_owners.json',folder/'audit.json',ledger_path]}
    app.write(folder/'terminal_seal.json',dict(all_passed=True,files=seal,case=case,geographic_inputs=False,
        raw_protocol_sha256=upstream,application_protocol_sha256=app.sha(app.RAW/'protocol.json')))
    print({k:audit[k] for k in ['case','new_native_owners','new_in_graph','new_in_curved_graph','baseline_equivalent_inputs','seconds']},flush=True)

def prepare():
    files=[Path(__file__),HERE/'test_handoff.py',app.R01/'validation/coherent_application/integrate.py',
        app.R01/'validation/prepare_overlay.py',app.R01/'validation/integration.py',
        REPO/'src/leo/analysis/graph_tracklets.py',REPO/'src/leo/analysis/polynomial_tracklets.py',
        REPO/'tools/evaluate_ds22_public_tracks.py',REPO/'tools/evaluate_ds22_merged_tracks.py',
        REPO/'tools/localize_merged_track_catalogue.py',REPO/'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json']
    for case in app.cohort()[1]:
        files.extend([app.SOURCE/case/n for n in ['observations.json','tracks.json','bank.npz','nominal_elements.json']])
        files.append(app.SOURCE/'causal_prior'/case/'receipt.json')
    app.write(HERE/'graph_protocol.json',dict(files={str(p):app.sha(p) for p in files},
        no_position_inference=True,all_original_prefix_exact=True,maximum_workers=2,cap_seconds=120))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','case']);p.add_argument('--case');a=p.parse_args()
    prepare() if a.action=='prepare' else main(a.case)
