"""Saved metadata only: active likelihood families without physical-mode slots."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    info=read(ROOT/'information/results.json');inventory=read(ROOT/'information/inventory.json')
    bindings={};rows=[];summaries=[]
    for frozen in inventory['cases']:
        case=frozen['case'];parentpath=SOURCE/'family_cavity/position'/f'{case}.json'
        trackpath=SOURCE/case/'tracks.json';ledgerpath=Path(frozen['parent_ownership_path'])
        for path in (parentpath,trackpath,ledgerpath):bindings[str(path)]=sha(path)
        parent=read(parentpath);tracks={t['key']:t for t in read(trackpath)};ledger=read(ledgerpath)
        node=parent['selected']['node'] if parent['accepted'] else parent['baseline_node']
        entries=parent['selected']['entries'] if parent['accepted'] else parent['baseline_entries']
        mask=parent['original_mask'];families={};cursor=0
        for row in node['seed']['rows']:
            if not row['active_curvature']:continue
            t=tracks[row['component']];n=len(t['observation_ids']);keep=mask[cursor:cursor+n];cursor+=n
            assert len(keep)==n
            j=row['candidate_index']
            family=families.setdefault(j,dict(case=case,candidate_index=j,norad=row['candidate_norad'],graph_owners=set(),
                graph_fragments=[],active_curved_fragments=[],predictive_fragments=[],curved_ids=[],predictive_ids=[]))
            owner=(t['receiver'],t['channel']);family['graph_owners'].add(owner)
            family['graph_fragments'].append(dict(component=t['key'],receiver=t['receiver'],channel=t['channel'],raw_points=n,used_points=sum(keep)))
            if any(keep):
                family['active_curved_fragments'].append(dict(component=t['key'],receiver=t['receiver'],channel=t['channel'],points=sum(keep)))
                family['curved_ids'] += [oid for oid,use in zip(t['observation_ids'],keep,strict=True) if use]
        assert cursor==len(mask)
        for e in entries:
            family=families[e['candidate_index']];t=tracks[e['component']]
            assert e['observation_ids']==t['observation_ids']
            family['predictive_fragments'].append(dict(component=t['key'],receiver=t['receiver'],channel=t['channel'],points=len(e['observation_ids'])))
            family['predictive_ids'] += e['observation_ids']
        active=[]
        for j,family in families.items():
            if not family['curved_ids'] and not family['predictive_ids']:continue
            key=str(family['norad']);mode_by_arm={};phase_by_arm={}
            for arm in ('c0','fitted_c'):
                mapping=next(p['role_map'] for p in info['parents'] if p['case']==case and p['arm']==arm)
                mode_by_arm[arm]=mapping['physical_modes'].get(key,[])
                phase_by_arm[arm]=mapping['phase'].get(key)
                assert bool(mode_by_arm[arm]) == (len(family['graph_owners'])>=2)
            assert bool(mode_by_arm['c0'])==bool(mode_by_arm['fitted_c'])
            allids=family['curved_ids']+family['predictive_ids'];assert len(allids)==len(set(allids))
            family.update(graph_owners=sorted(map(list,family['graph_owners'])),
                graph_fragment_count=len(family['graph_fragments']),active_curved_fragment_count=len(family['active_curved_fragments']),
                curved_points=len(family['curved_ids']),predictive_points=len(family['predictive_ids']),
                physical_mode_columns=mode_by_arm,phase_columns=phase_by_arm,
                physical_mode_prior_present=bool(mode_by_arm['c0']),
                predictive_only=not bool(family['curved_ids']),identity_qualified_by_this_inventory=False)
            active.append(family);rows.append(family)
        for arm in ('c0','fitted_c'):
            assert set(oid for f in active for oid in f['curved_ids'])==set(ledger['coverage'][arm]['curved_observation_ids'])
            assert set(oid for f in active for oid in f['predictive_ids'])==set(ledger['coverage'][arm]['predictive_observation_ids'])
        missing=[f for f in active if not f['physical_mode_prior_present']]
        summaries.append(dict(case=case,active_likelihood_families=len(active),without_physical_modes=len(missing),
            missing_mode_norads=[f['norad'] for f in missing],curved_points_without_modes=sum(f['curved_points'] for f in missing),
            predictive_points_without_modes=sum(f['predictive_points'] for f in missing),
            multiple_curved_fragments_without_modes=[f['norad'] for f in missing if f['active_curved_fragment_count']>=2],
            predictive_only_without_modes=[f['norad'] for f in missing if f['predictive_only']]))
    sourcepaths=[REPO/'tools/dsx01_joint_marginal.py',REPO/'tools/ds23_height_problem.py',REPO/'tools/ds23_predictive_linear.py',
        REPO/'tools/ds23_frequency_events.py',REPO/'tools/dsx01_all_candidate_uncertainty.py',REPO/'tools/build_dsx01_orbit_modes.py',
        ROOT/'information/results.json',ROOT/'information/ranking.py',Path(__file__)]
    bindings.update({str(path):sha(path) for path in sourcepaths})
    output=dict(all_metadata_checks_passed=True,cases=summaries,families=rows,bindings=bindings,
        support_rule='JointMarginal: >=2 distinct (receiver,channel) pairs among original active-curvature seed rows, not >=2 source fragments and not recalculated from current keep mask',
        omitted_covariance='For an unsupported family no three physical-mode coordinates are constructed, so neither curved nor old-predictive design includes their covariance. Orbital phase, shared radio, source constants and measurement uncertainty remain.',
        earlier_mechanism='tools/dsx01_all_candidate_uncertainty.py: expand_uncertainty() already extends prior modes to every graph label independently of radio owner support; no new implementation or evaluation here',
        propagation_calls=0,fits=0,GPS_or_position_errors_read=False)
    (ROOT/'audit/shape_support_inventory.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(summaries,indent=2))


if __name__=='__main__':main()
