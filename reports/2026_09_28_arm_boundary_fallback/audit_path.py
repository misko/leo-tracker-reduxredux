"""Independently audit which output path each fallback candidate used."""
import argparse
import hashlib
import json
from pathlib import Path


def load(folder):
    manifest=json.loads((folder/'manifest.json').read_text())
    assert manifest['complete']
    out={}
    for line in (folder/'rows.jsonl').read_text().splitlines():
        row=json.loads(line);ctx=row['context'];key=(ctx['session_id'],ctx['visit_index'])
        assert key not in out and row['returncode']==0 and not row['stderr']
        windows={}
        for w in row['rows']:
            wk=(w['receiver_id'],w['probe_index']);assert wk not in windows
            candidates={(c['coarse_epoch'],c['coarse_bin']):c for c in w['candidates']}
            assert len(candidates)==len(w['candidates'])==8
            windows[wk]=(w,candidates)
        assert set(windows)=={(rx,i) for rx in (0,1) for i in range(11)}
        out[key]=(ctx,windows)
    assert len(out)==manifest['processed_dwells']
    return out


def audit(candidate,direct,full):
    got=load(candidate);fast=load(direct);original=load(full)
    counts=dict(dwells=len(got),windows=0,candidate_entries=0,conditioned_fallbacks=0,
                direct_results=0,positive_proposal_comparisons=0,positive_proposals_matching_full=0)
    counts['baseline_negative_windows_now_positive']=0
    fields=('epoch','acquired_cfo_hz','tracking_cfo_hz','exact_score','control_score','margin')
    for case,(ctx,windows) in got.items():
        assert ctx['sha256']==fast[case][0]['sha256']==original[case][0]['sha256']
        for wk,(row,candidates) in windows.items():
            counts['windows']+=1
            _,f=fast[case][1][wk];_,o=original[case][1][wk]
            assert candidates.keys()==f.keys()==o.keys()
            counts['baseline_negative_windows_now_positive']+=(
                not any(c['margin']>=.025 for c in o.values()) and
                any(c['margin']>=.025 for c in candidates.values()))
            fallback_count=0
            for key,c in candidates.items():
                d=f[key];b=o[key]
                residual=d['tracking_cfo_hz']-d['acquired_cfo_hz']
                # Discrete 443.89Hz bins lie far from the 1000Hz guard edge.
                flagged=abs(abs(residual)-1/(2*4.4e-6))<=1000
                assert bool(c['conditioned_fallback'])==flagged
                expected=b if flagged else d
                for field in fields:
                    assert c[field]==expected[field],(case,wk,key,field)
                assert c['glrt_complete']==1
                assert c['acquire_score'] is None and c['verify_score'] is None and c['verify_control_score'] is None
                if flagged:
                    assert c['conditioned_cfo_hz']==b['conditioned_cfo_hz']
                    assert c['conditioned_score']==b['conditioned_score']
                else:
                    assert c['conditioned_cfo_hz'] is None and c['conditioned_score'] is None
                fallback_count+=flagged
                counts['candidate_entries']+=1
                if b['margin']>=.025:
                    counts['positive_proposal_comparisons']+=1
                    counts['positive_proposals_matching_full']+=(c['margin']>=.025 and abs(c['tracking_cfo_hz']-b['tracking_cfo_hz'])<=8000)
            counts['conditioned_fallbacks']+=fallback_count
            counts['direct_results']+=len(candidates)-fallback_count
            if 'conditioned_fallback_count' in row:
                assert row['conditioned_fallback_count']==fallback_count
    counts['actual_glrt_kernel_calls']=counts['candidate_entries']+counts['conditioned_fallbacks']
    return dict(scope='Exact per-coarse-proposal path audit; scientific hit recovery is scored separately',
                counts=counts,all_computed_final_fields_match_expected_path=True,
                candidate_rows_sha256=hashlib.sha256((candidate/'rows.jsonl').read_bytes()).hexdigest())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','direct','full','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();x=audit(a.candidate,a.direct,a.full);a.output.write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x['counts'],indent=2))
