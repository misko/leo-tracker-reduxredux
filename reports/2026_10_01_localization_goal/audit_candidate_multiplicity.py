"""Count multi-prediction candidate groups without interpreting them as emitters."""
import json
import time
from collections import Counter
from pathlib import Path

from candidate_cached_joint import CandidateJointObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    started = time.monotonic()
    freeze = HERE/'vectorized-proposals-v1/sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    sources = frozen['source_sha256']
    sources[str(Path(__file__))] = digest(__file__)
    verify_sources(sources)
    rows = []
    for unit, arm in frozen['pairs']:
        if arm != 'candidate':
            continue
        path = freeze.parent/(unit+'-candidate.json')
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        receipt = json.loads(path.read_text())
        assert receipt['converged']
        model = CandidateJointObjective(unit, state=receipt['full_state'],
                                        assignments=receipt['assignments'])
        assert abs(model.evaluate(model.initial, gradient=False)[0]
                   -receipt['final_objective']) < 1e-7
        means = model.base.predictions(model.initial[:2])
        slot_identities = []
        for query, index, _, n, _, _, _ in model.prepared:
            slot_identities.extend([index]*(len(query.times)-n))
        counts, distinct, separated = Counter(), Counter(), 0
        for group, slots in zip(model.base.groups, model.base.group_slots, strict=True):
            n, m = len(group['candidates']), len(slots)
            unique = len({slot_identities[i] for i in slots})
            counts[(n, m)] += 1
            distinct[(n, unique)] += 1
            # Distinct inferred satellites separated by more than2likelihood scales.
            found = False
            for i, first in enumerate(slots):
                for second in slots[i+1:]:
                    if slot_identities[first] == slot_identities[second]:
                        continue
                    delta = abs((means[first]-means[second]+group['period']/2)
                                % group['period']-group['period']/2)
                    found |= delta > 400.
            separated += bool(n >= 2 and found)
        rows.append(dict(unit=unit, parent_sha256=digest(path),
            groups=len(model.base.groups),
            histogram=[dict(candidates=n, predictions=m, groups=c)
                       for (n, m), c in sorted(counts.items())],
            distinct_histogram=[dict(candidates=n, satellites=m, groups=c)
                                for (n, m), c in sorted(distinct.items())],
            multiple_candidates_and_predictions=sum(c for (n, m), c in counts.items()
                                                     if n >= 2 and m >= 2),
            multiple_candidates_and_distinct_satellites=sum(c for (n, m), c in distinct.items()
                                                            if n >= 2 and m >= 2),
            separated_distinct_satellite_groups=separated))
    verify_sources(sources)
    summary = {key: sum(r[key] for r in rows) for key in ['groups',
        'multiple_candidates_and_predictions', 'multiple_candidates_and_distinct_satellites',
        'separated_distinct_satellite_groups']}
    result = dict(rows=rows, summary=summary, source_sha256=sources,
        elapsed_s=time.monotonic()-started,
        qualification='Coverage diagnostic at12sealed inferred states, no GPS or fitting. '
        'Multiple predictions are active trajectory hypotheses, not verified simultaneous '
        'emitters. Multiple admitted detector peaks may be aliases or false detections. '
        '400Hz separation is descriptive twice the existing engineering likelihood scale.')
    output = HERE/'candidate-multiplicity-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(summary=summary, elapsed_s=result['elapsed_s']), indent=2))


if __name__ == '__main__':
    main()
