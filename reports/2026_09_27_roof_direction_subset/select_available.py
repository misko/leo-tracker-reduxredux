"""Select a separate readiness-only cohort before any reception-model scoring."""
import json
from datetime import datetime, timezone
from prepare import HERE, ROOT, POSE, validate_pose, select_subset
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis


def main():
    target = HERE / 'evaluation_manifest.json'
    if target.exists():
        raise FileExistsError('availability cohort is already frozen')
    original = json.loads((HERE/'manifest.json').read_text())
    cutoff = max(x['pose']['capture_start_earliest_utc_ns'] for x in original['sessions'])
    captures = AdaptiveHopIqStore(ROOT, read_only=True)
    analyses = AdaptiveHopAnalysisStore(ROOT, read_only=True)
    inventory = []; eligible = []
    try:
        poses = sorted((json.loads(p.read_text()) for p in POSE.glob('*.json')), key=lambda p:p['capture_start_earliest_utc_ns'])
        for p in poses:
            if p['capture_start_earliest_utc_ns'] > cutoff:
                continue
            validate_pose(p)
            cap = captures.inspect(p['session_id'])
            if cap.manifest_sha256 != p['manifest_sha256']:
                raise ValueError('source digest mismatch')
            binding = bind_actual_visit_analysis(cap.manifest.receipt, input_manifest_sha256=cap.manifest_sha256, probe_stride_ms=120)
            with analyses.job(binding) as job:
                ready = job.manifest() is not None
            inventory.append(dict(session_id=p['session_id'], capture_start_utc_ns=p['capture_start_earliest_utc_ns'], ready=ready))
            if ready:
                eligible.append(p)
            print(p['session_id'], ready, flush=True)
        selected = select_subset(eligible, count=10, calibration_count=6)
        target.write_text(json.dumps(dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),
            selection='Supplemental readiness-only cohort before reception scoring: newest10 authoritative complete analyses by capture time, first6calibration final4holdout. Cutoff inherited from original12 freshness cohort; all original accounting retained.',
            inventory=inventory, sessions=selected), indent=2)+'\n')
        print('SELECTED', [(x['pose']['session_id'],x['split']) for x in selected], flush=True)
    finally:
        captures.close(); analyses.close()


if __name__ == '__main__':
    main()
