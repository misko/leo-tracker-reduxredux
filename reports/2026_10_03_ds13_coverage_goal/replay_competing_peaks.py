"""Bounded raw-IQ replay of close competing hypotheses; diagnostic only.

Uses public read-only storage and conditioned GLRT scoring interfaces. Does not
modify source recordings, assignments or the frozen coverage denominator.
"""
import argparse,hashlib,json,sys,time
from pathlib import Path
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,digest


def select_pairs(pairs,metadata,limit=2):
    selected=[];visits=set()
    for pair in pairs:
        r,s=metadata[pair['row_index']],metadata[pair['nearest_assigned_row']]
        if pair['frequency_distance_hz']>50 or pair['frame_epoch_distance_samples']>.01:continue
        if r['integer_epoch_sample']!=s['integer_epoch_sample']:continue
        if abs(r['acquired_cfo_hz']-s['acquired_cfo_hz'])>50:continue
        if r['probe_key'][2]!=0 or r['probe_key'][0] in visits:continue
        selected.append(pair);visits.add(r['probe_key'][0])
        if len(selected)>=limit:break
    return selected


def sample_visits(pairs,metadata,limit=8,seed=20261003):
    eligible=select_pairs(pairs,metadata,limit=max(1,len(pairs)))
    order=np.random.default_rng(seed).permutation(len(eligible))[:limit]
    return [eligible[int(i)] for i in order],len(eligible)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expanded',action='store_true');args=parser.parse_args()
    sys.path.insert(0,str(OLD));import exhaustive_subset
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
    output=ROOT/('raw-peak-expanded' if args.expanded else 'raw-peak-replay');output.mkdir(exist_ok=True)
    target=output/'replay.json'
    if target.exists():raise FileExistsError(target)
    store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True);results=[];started=time.monotonic();selection={}
    try:
        for scan,session in SESSIONS.items():
            source=ROOT/'peak-provenance'/f'{scan}-families.json';audit=json.loads(source.read_text())
            bundle_path=ROOT.parent/'2026_10_02_ds13_timing_em/scans'/session/'bundle.json'
            bundle=json.loads(bundle_path.read_text());metadata=bundle['alias_grouping']['representative_rows']
            published=store.inspect(session)
            if published.manifest_sha256!=bundle['provenance']['input_manifest_sha256']:raise ValueError('IQ binding changed')
            fs=int(published.manifest.receipt.plan.geometry.sample_rate_hz)
            if args.expanded:
                pairs,eligible=sample_visits(audit['pairs'],metadata,seed=20261003+(scan=='B'))
                selection[scan]=dict(eligible_visits=eligible,selected_visits=len(pairs),seed=20261003+(scan=='B'))
            else:pairs=select_pairs(audit['pairs'],metadata)
            for pair in pairs:
                if time.monotonic()-started>120:raise TimeoutError('Bounded replay exceeded 120 seconds')
                rows=[metadata[pair[k]] for k in ('row_index','nearest_assigned_row')]
                visit_index,rx,_=rows[0]['probe_key'];visit,iq=store.read_visit_ci16(published,visit_index)
                probe=iq[:fs//50,rx,:] # persisted probe index zero: first 20 ms of valid visit
                samples=(probe[:,0].astype(float)+1j*probe[:,1].astype(float))/32768.
                edge=visit.event.target.edge;replayed=[]
                for row in rows:
                    score=conditioned_glrt64_score(samples,fs,epoch_sample=row['integer_epoch_sample'],
                        acquired_cfo_hz=row['acquired_cfo_hz'],edge=edge,
                        fractional_epoch_offset_samples=row['fractional_epoch_offset_samples'])
                    replayed.append(dict(exact_score=score.exact_score,margin=score.margin,
                        tracking_cfo_hz=score.tracking_cfo_hz,
                        persisted_exact_score=row['candidate_spec']['fractional_exact_score'],
                        persisted_margin=row['fractional_margin']))
                matches=all(abs(r['exact_score']-r['persisted_exact_score'])<1e-4 and abs(r['margin']-r['persisted_margin'])<1e-4 for r in replayed)
                profile=[]
                if matches and not args.expanded:
                    center=np.mean([r['acquired_cfo_hz'] for r in rows])
                    for offset in np.linspace(-200,200,41):
                        score=conditioned_glrt64_score(samples,fs,epoch_sample=rows[0]['integer_epoch_sample'],
                            acquired_cfo_hz=float(center+offset),edge=edge,
                            fractional_epoch_offset_samples=rows[0]['fractional_epoch_offset_samples'])
                        profile.append(dict(acquired_cfo_hz=float(center+offset),exact_score=score.exact_score,margin=score.margin,
                                            tracking_cfo_hz=score.tracking_cfo_hz))
                result=dict(scan=scan,session_id=session,pair=pair,probe_key=rows[0]['probe_key'],
                    acquired_cfo_hz=[r['acquired_cfo_hz'] for r in rows],replay_matches_persisted=matches,replayed=replayed,profile=profile,
                    input_manifest_sha256=published.manifest_sha256,probe_ci16_sha256=hashlib.sha256(probe.tobytes()).hexdigest(),
                    sample_rate_hz=fs,probe_samples=len(probe),source_sha256={str(p):digest(p) for p in (source,bundle_path)})
                results.append(result);print(scan,rows[0]['probe_key'],'reproduces',matches,replayed,flush=True)
    finally:store.close()
    with target.open('x') as stream:json.dump(dict(scope=__doc__,results=results,selection=selection,elapsed_s=time.monotonic()-started,
        limitations=['Expanded run: seeded uniform sample of up to eight eligible visits per scan, using first eligible pair per visit. Original run: first two eligible visits. Neither represents all GLRT peaks.',
            'Conditional single-source profile at a fixed epoch, not a one-source-versus-two-source likelihood test.',
            'No claims of duplicate physical signals or confirmed satellite identities.']),stream,indent=2)


if __name__=='__main__':main()
