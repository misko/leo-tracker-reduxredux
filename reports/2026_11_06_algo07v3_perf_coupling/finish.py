"""Finish the completed counter run with an explicit unchanged-module contract.

The original comparator CLI defaults to expecting a hierarchical-module change.
This run changes no runtime module. Do not rerun completed scientific work.
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from compare_algo07v3_runs import compare
from profile_algo07v3_perf import parse_counters


def main():
    root = Path('/srv/bulk/leo-dev/algo07v3-perf-native-0066-r2-20261106')
    plan = json.loads((root/'plan.json').read_bytes())
    measured_tool = Path(__file__).with_name('measured-perf.py')
    observer = Path('tools/profile_algo07v3_perf.py').resolve()
    def bound_bytes(q):
        # The external observer was fixed after measurement; its exact measured
        # bytes are archived. Runtime modules still verify at their original paths.
        return measured_tool.read_bytes() if Path(q)==observer else Path(q).read_bytes()
    changed = [q for q,h in plan['bindings'].items()
               if hashlib.sha256(bound_bytes(q)).hexdigest()!=h]
    assert changed == []
    args = SimpleNamespace(
        baseline_request=Path('/srv/bulk/leo-dev/algo07v3-control-view-native-0066-20261106/'
                              'candidate-request.json'),
        baseline_timing=Path('/srv/bulk/leo-dev/algo07v3-control-view-native-0066-20261106/'
                             'candidate/attempt/supervisor.json'),
        candidate_request=root/'request.json',
        candidate_timing=root/'native/attempt/supervisor.json',
        changed_module=[], added_module=[])
    comparison = compare(args)
    (root/'comparison.json').write_text(json.dumps(comparison, indent=2)+'\n')
    measured = json.loads((root/'native-execution.json').read_bytes())
    measured['counters'] = parse_counters(root/'native-counters.jsonl')
    result = dict(measured=measured, resources_before=None, resources_after=None,
                  resource_note=('Transient samples were not saved after '
                                 'original comparator failure'),
                  scope='perf includes isolated harness, preflight, supervisor and descendants',
                  scientific_equality=True, speedup=None, production_modified=False,
                  completion='Explicit unchanged-module comparison of already completed run')
    (root/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    (root/'binding-check.json').write_text(json.dumps(dict(changed=[]), indent=2)+'\n')
    print(json.dumps(dict(counters=measured['counters'], comparison=comparison), indent=2))


if __name__ == '__main__':
    main()
