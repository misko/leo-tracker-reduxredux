"""Descriptive extra-hypothesis audit; not a calibrated real-track classifier."""
import json
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
BASE = REPORTS / '2026_09_30_arm_fast_tracks/server-baseline/output'
NEW = REPORTS / '2026_10_01_arm_ungated_full_scan/analysis'
sys.path.insert(0, str(REPORTS / '2026_09_30_arm_curvature_tracks/evaluation'))
import compare_membership as m


def main():
    so = m.read_observations(BASE / 'server-observations.tsv')
    ss = m.read_sources(BASE / 'server-candidate-map.tsv', so)
    obs = m.read_observations(NEW / 'observations.tsv')
    sources = m.read_sources(NEW / 'candidate-map.tsv', obs)
    refs = m.read_tracks(BASE / 'server-tracks.tsv', so).values
    # All 63 references provide descriptive evidence, including excluded #10.
    evidence = {}
    for ref in refs:
        for p in ref.points:
            evidence.setdefault((ref.lane, ss[p.candidate]), []).append(p.raw_cfo_hz)
    summaries = []
    for name in ['rolling', 'kalman-v2', 'linking-v2', 'coarse-seeded', 'rolling-backfill']:
        path = NEW / 'tracks-0.tsv' if name == 'rolling-backfill' else HERE / name / 'tracks-0.tsv'
        tracks = m.read_tracks(path, obs).values
        evaluation = json.loads((HERE / name / 'evaluation.json').read_text())
        extra_ids = set(evaluation['primary']['unmatched_output_indexes'])
        rows = []
        for tr in tracks:
            if tr.index not in extra_ids:
                continue
            points = sorted(tr.points, key=lambda p: obs[p.candidate].center_ns)
            origin = obs[points[0].candidate].center_ns
            t = np.array([(obs[p.candidate].center_ns-origin)*1e-9 for p in points])
            f = np.array([p.dealiased_cfo_hz for p in points])
            spacing = 11.2e9 / tr.lane.rf_hz / 4.4e-6
            supported = {sources[p.candidate] for p in points if any(
                m.circular_distance(p.raw_cfo_hz-v, spacing) <= 2500
                for v in evidence.get((tr.lane, sources[p.candidate]), []))}
            n_sources = len({sources[p.candidate] for p in points})
            errors = []
            for i in range(5, len(points)):
                mask = t[:i] >= t[i]-8
                if sum(mask) < 5 or t[i]-t[i-1] > 4 or np.ptp(t[:i][mask]) < 2:
                    continue
                fit = np.polyfit(t[:i][mask]-t[i], f[:i][mask], 1)
                errors.append(m.circular_distance(f[i]-fit[1], spacing))
            # Fixed before observing results: require meaningful causal evidence,
            # local continuity and the existing 2.5 kHz comparison tolerance.
            enough = len(errors) >= 5 and len(errors) >= .5*len(points)
            p95 = float(np.percentile(errors, 95)) if errors else None
            smooth = bool(enough and p95 <= 2500 and np.max(np.diff(t)) <= 4)
            rows.append(dict(output_index=tr.index, points=len(points), span_s=float(np.ptp(t)),
                reference_supported_sources=len(supported), source_count=n_sources,
                reference_support_fraction=len(supported)/n_sources,
                causal_predictions=len(errors), causal_p95_hz=p95,
                adequate_prediction_evidence=bool(enough), continuity_screen_pass=smooth))
        strong = [r for r in rows if r['reference_support_fraction'] >= .8]
        novel = [r for r in rows if r['reference_supported_sources'] == 0]
        plausible = [r for r in rows if r['reference_support_fraction'] >= .8 or r['continuity_screen_pass']]
        summary = dict(method=name, total_outputs=len(tracks), additional_outputs=len(rows),
            excess_over_62=len(tracks)-62, strongly_reference_supported=len(strong),
            continuity_screen_pass=sum(r['continuity_screen_pass'] for r in rows),
            supported_or_continuous=len(plausible),
            no_reference_support=len(novel),
            no_reference_support_continuous=sum(r['continuity_screen_pass'] for r in novel))
        assert len(rows) == len(tracks)-evaluation['primary']['complete_one_to_one_count']
        (HERE/name/'additional-tracks.json').write_text(json.dumps(rows, indent=2)+'\n')
        summaries.append(summary)
    (HERE/'additional-summary.json').write_text(json.dumps(summaries, indent=2)+'\n')
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
