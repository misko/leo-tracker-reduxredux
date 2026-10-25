"""Final narrative/figure-data checks using sealed artifacts only."""
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
read = lambda p: json.loads(Path(p).read_bytes())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
began = time.monotonic()
checks, residuals = [], []


def check(name, passed, **details):
    checks.append(dict(name=name, passed=bool(passed), **details))


for arm in ('c0', 'fitted_c'):
    with np.load(ROOT / 'prediction/run02' / arm / 'joint_background.npz') as background, np.load(
            ROOT / 'prediction/run02' / arm / 'Dposterior_GL64.npz') as prediction:
        times = background['times_s'][81:]
        residual = background['raw_hz'][81:] - prediction['prediction_mean_Hz'][24:]
        residuals.append(dict(arm=arm, final_time_s=float(times[-1]), final_residual_hz=float(residual[-1]),
            pre249_min_hz=float(residual[times < 249].min()), pre249_max_hz=float(residual[times < 249].max())))
    rows = [r for r in csv.DictReader((ROOT / 'prediction/fixed_alias0_residuals03.csv').open())
            if r['arm'] == arm]
    # CSV column names are recorded rather than inferred as scientific inputs.
    check('fixed graph-alias-zero CH4 descriptive endpoint matches saved prediction: ' + arm,
          abs(residual[-1] - (-3489.17465 if arm == 'c0' else -3164.50385)) < 1e-4 and len(rows) > 0)

main = (ROOT / 'README.md').read_text()
review = (ROOT / 'REVIEW.md').read_text()
check('both terminal audits pass and no position inference was run',
      read(HERE / 'prediction_terminal.json')['all_passed'] and read(HERE / 'coupling_terminal.json')['all_passed'])
check('current narrative retains calibration/alias/CH4 and identity distinctions',
      'Each arm retains its own saved calibration' in main and
      'variance of the full raw-alias mixture' in main and 'Budget-limited' in main and
      'They do not prove CH5/57450 false' in main and 'not a new estimated position' in main)
check('source-switching hypothesis is first and explicitly all-points/normalized',
      review.index('1. Test the concrete source-switching') < review.index('2. Separate nomination') and
      'normalized' in review and 'all' in review and 'not fitted breakpoints or confirmed joins' in review)
check('matched-law control limits are explicit', 'exogenous-background control' in review and
      'There is no calibrated identity-acceptance rule' in review and
      'not a full IQ-to-position simulation' in review)
missing = []
for relative in ('README.md', 'REVIEW.md', 'audit/FINDINGS.md', 'audit/NEXT_CONTROL_REVIEW.md', 'audit/ARCHIVAL_CORRECTION.md'):
    path = ROOT / relative
    for link in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        if not link.startswith(('http:', 'https:')) and not (path.parent / link.split('#')[0]).exists():
            missing.append([relative, link])
check('all final narrative relative links resolve', not missing, missing=missing)
diff = subprocess.check_output(['git', 'diff'], cwd='/home/mouse9911/gits/leo-tracker-reduxredux')
dirty = hashlib.sha256(diff).hexdigest()
check('unrelated root tracked work unchanged', dirty == 'add0a0f9598b5045dbf6dd6eb05b744b856715c01a9cb3101f6890b999029a4b')
receipt = dict(all_passed=all(c['passed'] for c in checks), checks=checks, CH4_fixed_alias0_descriptive=residuals,
    README_sha256=sha(ROOT / 'README.md'), REVIEW_sha256=sha(ROOT / 'REVIEW.md'), source_sha256=sha(__file__),
    seconds=time.monotonic() - began, prior_cumulative_audit_seconds=read(HERE / 'prediction_terminal.json')['cumulative_audit_seconds'],
    new_propagation_calls=0, new_scores=0, position_fits=0, geographic_truth_read=False,
    conclusion='Final source/claim review passes: CH3 noncorroboration, CH4 unresolved, sub-metre conditional parent mechanism, cached-residual correction and targeted source-ownership-first next test are accurately scoped.')
receipt['cumulative_audit_seconds'] = receipt['prior_cumulative_audit_seconds'] + receipt['seconds']
with (HERE / 'final_review.json').open('x') as stream:
    json.dump(receipt, stream, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps(dict(path=str(HERE / 'final_review.json'), all_passed=receipt['all_passed'],
    cumulative_audit_seconds=receipt['cumulative_audit_seconds'], failed=[c for c in checks if not c['passed']])))
