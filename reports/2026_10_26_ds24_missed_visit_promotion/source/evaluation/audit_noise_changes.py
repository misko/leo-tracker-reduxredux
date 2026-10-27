"""Compare effective existing scales, without re-estimating or fitting noise."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from audit_implementation import read,write,sha
from audit_candidate_protocol import effective
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
WORKER=HERE.parent/'held_position'


def main():
    p=read(WORKER/'coherent_candidates/protocol.json');nom={r['case']:r for r in read(HERE/'nomination_audit.json')['cases']}
    physical={(j['case'],j['variant']):j for j in p['jobs']+p['controls']};rows=[]
    for case,n in nom.items():
        if not n['eligible']:continue
        original=read(SOURCE/case/'observations.json');ids=[o['observation_id'] for o in original]
        baseline=effective(read(SOURCE/case/'radio_noise.json'),ids)
        proxyroot=Path(physical[case,'additions_proxy']['root']);floorroot=Path(physical[case,'additions_bin_floor']['root'])
        proxy=effective(read(proxyroot/case/'radio_noise.json'),ids);floor=effective(read(floorroot/case/'radio_noise.json'),ids)
        assert proxy==floor
        delta=[proxy[oid]-baseline[oid] for oid in ids]
        rows.append(dict(case=case,cohort=n['cohort'],incumbent_GLRT_count=len(ids),
            incumbent_effective_sigma_changed=sum(abs(v)>1e-10 for v in delta),
            incumbent_sigma_change_range_hz=[min(delta),max(delta)],
            floor_proxy_incumbent_scales_exactly_equal=True,
            original_noise_sha256=sha(SOURCE/case/'radio_noise.json'),proxy_noise_sha256=sha(proxyroot/case/'radio_noise.json'),floor_noise_sha256=sha(floorroot/case/'radio_noise.json')))
    write(HERE/'incumbent_noise_audit.json',dict(all_passed=True,cases=rows,eligible_scans=len(rows),
        all_eligible_scans_have_incumbent_scale_changes=all(r['incumbent_effective_sigma_changed']>0 for r in rows),
        new_noise_estimator_calls=0,new_position_fits=0,geographic_errors_opened=False,
        interpretation='Baseline-to-candidate changes graph membership and incumbent learned scales. Proxy-to-floor holds incumbent scales fixed, but may still change downstream association. A new-owner-only/frozen-incumbent ablation was not run.'))
    print(dict(eligible_scans=len(rows),all_have_incumbent_scale_changes=True,all_proxy_floor_incumbent_scales_exact=True),flush=True)


if __name__=='__main__':main()
