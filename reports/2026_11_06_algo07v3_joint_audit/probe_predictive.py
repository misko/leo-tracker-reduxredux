"""Use the tested checkpoint probe on the first predictive joint audit.

This changes only its interception predicate and scope label. Actual joint
arithmetic retains the original policy-free optimized contraction route.
Both this wrapper and the unmodified probe template enter the run bindings.
"""

from pathlib import Path


def main():
    path = Path('tools/probe_algo07v3_joint_audit.py')
    source = path.read_text()
    substitutions = {
        "if method != 'joint' or policy is None or policy.joint_contraction_optimized:":
            "if method != 'joint' or policy is not None:",
        'args.request, args.native_comparison, *qualified]':
            "args.request, args.native_comparison, *qualified, "
            "Path('tools/probe_algo07v3_joint_audit.py')]",
        'first native direct joint-audit quadrature':
            'first native predictive joint-audit quadrature',
    }
    for old, new in substitutions.items():
        if source.count(old) != 1:
            raise ValueError('Review changed checkpoint probe boundary: ' + old)
        source = source.replace(old, new)
    scope = dict(__name__='_predictive_audit_probe', __file__=str(Path(__file__).resolve()))
    exec(compile(source, '<predictive-audit-checkpoint-probe>', 'exec'), scope)
    scope['main']()


if __name__ == '__main__':
    main()
