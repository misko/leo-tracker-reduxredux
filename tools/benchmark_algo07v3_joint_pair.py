"""Compare serial and independent process execution of both actual joint fit arms."""

import time
from pathlib import Path

from benchmark_algo07v3_final_joint import main
from probe_algo07v3_joint_audit import cpu, signature

from leo.analysis.localization_v3.numerical_policy import map_calibration_arms
from leo.operations.localization_v3_parallel import _ordered


def fits(operation, args, parallel):
    context, targets, arm, method, step = args
    if arm != 'c0':
        raise ValueError('Both-arm comparison starts at original c0 checkpoint')

    def execute(arm):
        start, used = time.perf_counter(), cpu()
        result = operation(context, targets, arm, method, step)
        return dict(result=result, seconds=time.perf_counter()-start, cpu_seconds=cpu()-used)

    def mapper(fn, arms):
        return _ordered(fn, arms, workers=2)

    return map_calibration_arms(context, execute, ('c0', 'fitted_c'), mapper if parallel else None)


def measure(operation, args, save):
    rows, expected = [], None
    for index, side in enumerate(('baseline', 'candidate', 'candidate', 'baseline')):
        def trial(_, side=side):
            policy = args[0].get('numerical_policy')
            before = signature(policy.receipt) if policy else None
            start, used = time.perf_counter(), cpu()
            results = fits(operation, args, parallel=side == 'candidate')
            elapsed, used = time.perf_counter()-start, cpu()-used
            return dict(seconds=elapsed, cpu_seconds=used,
                        result=signature([r['result'] for r in results]),
                        arm_signatures=[signature(r['result']) for r in results],
                        arm_seconds=[r['seconds'] for r in results],
                        arm_cpu_seconds=[r['cpu_seconds'] for r in results],
                        policy_before=before,
                        policy_after=signature(policy.receipt) if policy else None)

        row = _ordered(trial, [0], workers=1)[0]
        science = row['result'], row['policy_before'], row['policy_after']
        if expected is None:
            expected = science
        row.update(index=index, side=side, exact=science == expected)
        save(row)
        rows.append(row)
        if not row['exact']:
            raise ValueError('Complete paired fits or ordered numerical receipts changed')
    return rows


if __name__ == '__main__':
    main(measurement=measure, scope='both native joint-fit arms; audits excluded',
         extra_dependencies=(Path(__file__),), export_candidates=False)
