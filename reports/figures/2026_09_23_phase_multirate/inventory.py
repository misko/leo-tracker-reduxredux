"""Read-only, phase-blind inventory of a frozen pre-rotation comparison cohort."""
import json
from pathlib import Path
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.scanner.adaptive_relative_phase import relative_phase_binding
from leo.storage.adaptive_relative_phase import RelativePhaseStore
from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs
from leo.application.adaptive_relative_phase import relative_phase_priority

OUT = Path(__file__).resolve().parent
COHORT = {
    'scan-fw-1aa1d50103d97388': 'User-requested 2.5 MS/s anchor',
    'scan-fw-25454cd8b0e8d9d1': 'Nearest preceding 10 MS/s in frozen pre-rotation window',
    'scan-fw-ef23302fda59d403': 'Nearest preceding 15 MS/s in frozen pre-rotation window',
    'scan-fw-9b88653c7a012fc2': 'Largest min(RX0,RX1) passing-candidate count among completed 10 MS/s scans in frozen table',
    'scan-fw-894676bdae3d7b2c': 'Largest min(RX0,RX1) passing-candidate count among completed 15 MS/s scans in frozen table',
}


def run():
    root = Path('/srv/bulk/leo')
    captures = AdaptiveHopIqStore(root, read_only=True)
    analyses = AdaptiveHopAnalysisStore(root, read_only=True)
    results = []
    for sid, reason in COHORT.items():
        pub = captures.inspect(sid)
        m = pub.manifest
        binding = bind_actual_visit_analysis(m.receipt, input_manifest_sha256=pub.manifest_sha256,
                                             probe_stride_ms=120)
        meta = dict(session_id=sid, reason=reason, input_manifest_sha256=pub.manifest_sha256,
                    binding_sha256=binding.sha256, sample_rate_hz=m.receipt.plan.geometry.sample_rate_hz,
                    timing=m.timing.model_dump(mode='json'),
                    geometry=None if m.receiver_geometry is None else m.receiver_geometry.model_dump(mode='json'),
                    terminal=m.receipt.terminal.model_dump(mode='json'),
                    configuration=binding.configuration.model_dump(mode='json'), visits=[])
        try:
            with analyses.job(binding) as job:
                if job.manifest() is None:
                    raise ValueError('Analysis incomplete')
                for v in job.published_visits():
                    pairs = _phase_blind_pairs(v)
                    meta['visits'].append(dict(visit_index=v.visit_index,
                        relative_time_s=(v.valid_start_counter-v.source_origin_counter)/meta['sample_rate_hz'],
                        target=v.target.model_dump(mode='json'), priority=relative_phase_priority(v),
                        paired_count=len(pairs), passing={str(rx):sum(c.passed_fractional_margin_gate
                            for p in v.probes if p.receiver_id==rx for c in p.candidates) for rx in (0,1)}))
            phase = RelativePhaseStore(root, read_only=True)
            try:
                with phase.job(sid, relative_phase_binding(pub.manifest_sha256,binding.sha256)) as job:
                    pm = job.manifest()
                    if pm:
                        meta['existing_phase'] = [job.visit(i).model_dump(mode='json') for i in pm.selected_visits]
            except Exception as exc:
                meta['phase_unavailable'] = f'{type(exc).__name__}: {exc}'
        except Exception as exc:
            meta['analysis_unavailable'] = f'{type(exc).__name__}: {exc}'
        selected = []
        for channel in range(1,5):
            candidates = [v for v in meta['visits'] if v['priority'] is not None and v['target']['channel']==channel]
            selected.extend(v['visit_index'] for v in sorted(candidates,key=lambda v:(-v['priority'],v['visit_index']))[:2])
        meta['selected_visits'] = selected
        dest = OUT/sid
        dest.mkdir(exist_ok=True)
        (dest/'inventory.json').write_text(json.dumps(meta,indent=2)+'\n')
        results.append(dict(session_id=sid, sample_rate_hz=meta['sample_rate_hz'], reason=reason,
                            visit_count=len(meta['visits']), paired_visits=sum(v['paired_count']>0 for v in meta['visits']),
                            multiple_pair_visits=sum(v['paired_count']>1 for v in meta['visits']),
                            passing={rx:sum(v['passing'][rx] for v in meta['visits']) for rx in ('0','1')},
                            selected_visits=selected))
        print(results[-1],flush=True)
    (OUT/'selection.json').write_text(json.dumps(results,indent=2)+'\n')
    captures.close()
    analyses.close()


if __name__ == '__main__':
    run()
