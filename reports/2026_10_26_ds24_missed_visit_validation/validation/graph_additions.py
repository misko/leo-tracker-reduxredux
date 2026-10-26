"""Rebuild the unchanged original graph for primary R02 new owners only."""
import copy
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
R01=Path('/srv/bulk/leo/research/ds24-missed-visit-r01/validation')
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
sys.path.insert(0,str(R01))
from prepare_overlay import rebuild_graph


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def stage_additions(original,candidates):
    rows=copy.deepcopy(original);ids={o['observation_id'] for o in original}
    for candidate in candidates:
        n=candidate['native'];oid=candidate['target_observation_id']
        if oid in ids:raise ValueError('new target already has a native owner')
        ids.add(oid)
        row={k:n[k] for k in ('observation_id','receiver','native_receiver_id','channel','time_s','actual_rf_hz')}
        row.update(measured_cfo_hz=candidate['measured_cfo_hz'],fractional_margin=candidate['confirmation_margin'])
        rows.append(row)
    assert rows[:len(original)]==original
    return rows


def main():
    manifest=read(HERE/'candidate_manifest.json');by_case={}
    for candidate in manifest['candidates']:by_case.setdefault(candidate['case'],[]).append(candidate)
    config=read(REPO/'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json')['config']
    output=HERE/'graphs';output.mkdir(exist_ok=False);summary=[]
    for case,candidates in sorted(by_case.items()):
        original=read(SOURCE/case/'observations.json');rows=stage_additions(original,candidates)
        tracks,graph=rebuild_graph(rows,case,config);new={c['target_observation_id'] for c in candidates}
        ids={oid for t in tracks for oid in t['observation_ids']};curved=set(graph['curved_observation_ids'])
        folder=output/case;folder.mkdir()
        write(folder/'observations.json',rows);write(folder/'tracks.json',tracks)
        row=dict(case=case,new_native=len(new),new_in_graph=len(new&ids),new_curved=len(new&curved),
            new_curved_ids=sorted(new&curved),new_unassociated=len(new-ids),
            existing_measurements_preserved=True,forced_satellite_identity=False,
            position_or_GPS_used=False,raw_rows_sha256=sha(folder/'observations.json'),graph_sha256=sha(folder/'tracks.json'))
        write(folder/'audit.json',row);summary.append(row)
    write(HERE/'graph_audit.json',dict(cases=summary,new_native=sum(r['new_native'] for r in summary),
        new_curved=sum(r['new_curved'] for r in summary),new_graph=sum(r['new_in_graph'] for r in summary),
        new_position_runs=0,causal_association_pending=True,held_validation_outcomes_opened=False,
        original_graph_config_sha256=sha(REPO/'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json')))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
