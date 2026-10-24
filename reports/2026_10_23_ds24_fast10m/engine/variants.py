"""Fresh reference and frozen native-offer variants; no truth access."""
from pathlib import Path
from types import SimpleNamespace
import argparse
import signal
import sys
import time
import traceback
import numpy as np
import ds24_engine as engine
import probe_ds23_graph_seeded_paths as paths
from run_algo01_ds23_sample import read,write
from run_ds23_combined_recovery_full import valid
from probe_ds23_frequency_events import summary

OUT=engine.OUT
sys.path.insert(0,str(OUT/'contrast'))
import contrast


def qualified(pair):
    return bool(valid(pair) and all(s.get('final_phase_change_s',0)<=.01 for s in pair.values()))


def package(d,pair,parent_cov,baseline,**extra):
    cov={a:paths.coverage(d,'default',a,s) for a,s in pair.items()}
    preserved=all(set(parent_cov[a]['accepted_observation_ids'])<=set(cov[a]['accepted_observation_ids']) for a in engine.ARMS)
    accepted=bool(qualified(pair) and preserved)
    return dict(arms=pair if accepted else baseline['arms'],coverage=cov if accepted else baseline['coverage'],
        candidate_arms=pair,candidate_coverage=cov,accepted=True,candidate_accepted=accepted,status='complete',
        fallback=None if accepted else 'baseline',all_parent_IDs_preserved=preserved,**extra)


def one(case):
    result_path=OUT/'results'/(case+'.json');result_path.parent.mkdir(exist_ok=True)
    if result_path.exists():return read(result_path)
    began=time.monotonic();result=dict(case=case,status='running',methods={})
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('bounded native stage')))
    try:
        d=engine.cavity_context(case)
        cov={a:paths.coverage(d,'default',a,s) for a,s in d['arms'].items()}
        baseline=dict(arms=d['arms'],coverage=cov,accepted=True,status='complete',fallback=None)
        result['methods']['baseline']=baseline
        old=read(OUT/case/'algo02_result.json');historical=engine.context(case,signed=False)
        result['methods']['algo02_historical']=dict(arms=historical['arms'],coverage={a:paths.coverage(historical,'default',a,s) for a,s in historical['arms'].items()},accepted=True,status='complete',fallback=None)
        folder=OUT/case/'native';folder.mkdir(exist_ok=True)
        paths.OUT=folder;paths.runner=SimpleNamespace(configure=lambda:None)
        paths.parent=lambda _: (d,cov,'default',None)
        signal.alarm(360);paths.one(case);signal.alarm(0)
        native=read(folder/(case+'.json'))['methods']['persistent5s']
        # Preserve the published cold native fit and bounded near-feasible rescue.
        import probe_ds23_iteration010_path_feasibility as feasible
        feasible.OUT=OUT/case/'native_feasibility';feasible.OUT.mkdir(exist_ok=True)
        feasible.binding=SimpleNamespace(configure=lambda:None,paths=paths,OUT=folder)
        signal.alarm(360);feasible.one(case);signal.alarm(0)
        rescue=read(feasible.OUT/(case+'.json'))
        chosen=rescue if rescue.get('accepted') else native
        selection=folder/(case+'_persistent5s_selection.json')
        fragments=read(selection)['selected'] if selection.exists() else []
        if not fragments:
            for name in ('native_full','native_full_matched','native_fixed','native_contrasts'):
                result['methods'][name]=dict(baseline,accepted=True,candidate_accepted=False,fallback='baseline',reason='no whole native paths pass fixed-parent gates')
        else:
            scan,entries=paths.native.append_native_paths(d['scan'],d['entries'],fragments,paths.native.receiver_basis(d['scan']))
            dd=dict(d,scan=scan,entries=entries)
            if 'arms' in chosen:
                result['methods']['native_full']=package(dd,chosen['arms'],cov,baseline,published_cold_native=True,constrained_rescue=bool(rescue.get('accepted')))
            else: result['methods']['native_full']=dict(baseline,accepted=True,candidate_accepted=False,fallback='baseline',reason=chosen.get('reason'))
            signal.alarm(360)
            matched={a:contrast.fit(dd,'default',a,paths,full=True) for a in engine.ARMS}
            signal.alarm(0)
            result['methods']['native_full_matched']=package(dd,matched,cov,baseline,parent_start=True,
                same_start_solver_budget_and_paths_as_contrasts=True)
            for name,frozen in [('native_fixed',True),('native_contrasts',False)]:
                signal.alarm(360)
                pair={a:contrast.fit(dd,'default',a,paths,frozen=frozen) for a in engine.ARMS}
                signal.alarm(0)
                result['methods'][name]=package(dd,pair,cov,baseline,mean_removed_per_predictive_path=not frozen,
                    position_fixed=frozen,shared_native_paths=True)
        result.update(status='complete',native_paths=len(fragments),no_GPS_or_future_TLE=True,
            baseline_scope='fresh ALGO02, causal signed prior, equal-assignment-prior family cavity; graph reentry omitted',
            same_native_paths_and_aliases_in_all_variants=True)
    except Exception as exc:
        result.update(status='failed',error=repr(exc),traceback=traceback.format_exc())
    finally:
        signal.alarm(0);result['seconds']=time.monotonic()-began;write(result_path,result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',required=True);args=p.parse_args();one(args.case)
