"""Whole-recording acquisition/graph counts and mechanism, no position data."""
import collections
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from audit_nomination import read,write,sha
BROADER=HERE.parent/'broader'


def main():
    nomination=read(HERE/'nomination_audit.json');rows=[];candidates=[]
    for case in nomination['cases']:
        name=case['case'];folder=BROADER/'graphs'/name;terminal=read(folder/'terminal_seal.json')
        assert terminal['all_passed']
        for path,h in terminal['files'].items():assert sha(path)==h,path
        a=read(folder/'audit.json');ledger=read(a['ledger_path']);assert sha(a['ledger_path'])==a['ledger_sha256']
        ids={r['target_observation_id'] for r in ledger['staged']};assert ids==set(a['new_native_ids'])
        for r in ledger['staged']:
            assert r['donor_count']==len({d['native_observation_id'] for d in r['donors']})
            candidates.append(dict(case=name,cohort=case['cohort'],observation_id=r['target_observation_id'],
                donor_count=r['donor_count'],zero_fft_bin=r['zero_fft_bin'],innovation_hz=r['innovation_hz'],
                width_exceeds_wrong_pilot_control=r['width_exceeds_wrong_pilot_control']))
        rows.append(dict(case=name,cohort=case['cohort'],eligible_lane=case['eligible'],
            original_GLRT_count=a['original_GLRT_count'],total_GLRT_count=a['total_GLRT_count'],
            added_native=a['new_native_owners'],new_graph=a['new_in_graph'],new_curved=a['new_in_curved_graph'],new_outside=a['new_outside_graph']))
    groups={}
    for cohort in ('held','development','all24'):
        chosen=rows if cohort=='all24' else [r for r in rows if r['cohort']==cohort]
        new=candidates if cohort=='all24' else [r for r in candidates if r['cohort']==cohort]
        counts={key:sum(r[key] for r in chosen) for key in ('original_GLRT_count','total_GLRT_count','added_native','new_graph','new_curved','new_outside')}
        assert counts['original_GLRT_count']+counts['added_native']==counts['total_GLRT_count']
        groups[cohort]=dict(counts,scans=len(chosen),eligible_scans=sum(r['eligible_lane'] for r in chosen),
            whole_recording_GLRT_count_increase_fraction=counts['added_native']/counts['original_GLRT_count'],
            zero_fft_bins=sum(r['zero_fft_bin'] for r in new),one_donor=sum(r['donor_count']==1 for r in new),
            donor_count_distribution=dict(collections.Counter(str(r['donor_count']) for r in new)),
            broad_widths=sum(r['width_exceeds_wrong_pilot_control'] for r in new))
    write(HERE/'all24_acquisition_graph_mechanism.json',dict(all_passed=True,cases=rows,groups=groups,new_native_rows=candidates,
        no_new_IQ_reads=True,no_position_or_prior_fits=True,no_geographic_errors_opened=True,
        unchanged_input_prefixes_and_graph_terminal_hashes_verified=True,
        distinct_from_sparse_panel_coverage=True))
    print(groups,flush=True)


if __name__=='__main__':main()
