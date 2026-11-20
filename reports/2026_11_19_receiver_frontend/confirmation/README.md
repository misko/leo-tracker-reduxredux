# Late pilot confirmation for native fractional proposals

The fixed-coordinate gate retained 92.9% of archive-matched native proposals on DS26-0036 and 100% on DS29-0082. It also retained 82.6% and 90.1% of the native-only proposals. All four samples missed the predeclared 15-point retention contrast. The proposed hard gate stopped at detector qualification. Position and conditional Doppler RMS are unmeasured for this modification in both calibration arms. [Protocol](PROTOCOL.md) · [Position receipts](positions.jsonl.gz)

| Recording and sample | Valid / scheduled visits | Archive-matched retained | Native-only retained | Retention contrast | Confirmation CPU median / P95 |
|---|---:|---:|---:|---:|---:|
| DS26-0036 trial | 56 / 56 | 86 / 93 | 74 / 91 | 11.2 points | 3.18 / 16.44 ms |
| DS26-0036 alternate | 56 / 56 | 70 / 75 | 49 / 58 | 8.9 points | 0.04 / 10.62 ms |
| DS29-0082 trial | 39 / 56 | 31 / 31 | 39 / 44 | 11.4 points | 0.04 / 12.56 ms |
| DS29-0082 alternate | 40 / 56 | 53 / 53 | 52 / 57 | 8.8 points | 0.04 / 13.79 ms |

The times are host CPU for the added stage after `native.analyze` on a single pinned CPU per recording. Visits with no passing native proposal contribute only dispatch overhead. Among visits with at least one passing native proposal, the four median measurements ranged from 7.05 to 9.05 ms and P95 from 11.29 to 17.73 ms. The timed path scores up to eight proposals per receiver and reuses results for identical geometry within a receiver. Each receipt binds window IQ hashes and records both signed regional scores, the resulting decision, the native candidate scores and whether a conditioned fallback ran. [DS26 trial](DS26-0036-trial.json.gz) · [DS26 alternate](DS26-0036-alternate.json.gz) · [DS29 trial](DS29-0082-trial.json.gz) · [DS29 alternate](DS29-0082-alternate.json.gz)

The measurement compares exact and 17-symbol rolled Qin pilot coding at the candidate's fixed fractional epoch and tracking CFO. It uses odd symbols in two later regions of each frame, with fractional references generated at the measured sample times. The original final fractional GLRT uses early symbols 2–65. Fine acquisition uses even symbols. Native regional timing selection uses phase-invariant lag correlations across the waveform, and conditioned boundary fallback can use the full coherent template. The confidence from the later symbols is therefore conditional on native proposal selection. [Measurement implementation](../../../tools/pipeline_eval/variants/pilot_confirmation.py)

Archive match labels compare detector outputs at the same receiver and visit with the published timing and aliased CFO tolerances. Per-candidate satellite truth was unavailable. Across both recordings, 214 of 250 native-only candidates had enough repeatable exact late-pilot evidence to pass, and 26 of 1,269 candidates below the original margin also passed the diagnostic scoring. On DS26 the gate removed 10 of 45 archive-matched proposals from conditioned fallback and two of 123 from the ordinary fine path. This asymmetry warrants preserving the fallback indicator whenever the waveform score is used for diagnosis.

The installed capture validators reproduced 33 exclusions in the scheduled DS29 samples and explicitly rejected one targeted visit per producer before either detector ran. The DS26 targeted exclusion is outside the scheduled sample. [DS26 exclusion](DS26-0036-exclusion.json) · [DS29 exclusion](DS29-0082-exclusion.json)

## Reproduce

Run from the repository root using the installed producer source and the archived Python environment. The raw-IQ reader authenticates each selected manifest, index and window. The separate exclusion worker opens only the selected sealed chunk through the installed recording reader.

```sh
.venv/bin/python - <<'PY'
import os
import subprocess
from pathlib import Path

from tools.pipeline_eval.qualification.full_v5_check import PRODUCERS, REPO
from tools.pipeline_eval.qualification.pilot_confirmation_trial import write_predictions
from tools.pipeline_eval.qualification.recording_to_v5 import ARCHIVE_PYTHON, SINGLE_THREAD

out = Path('/tmp/late-pilot-confirmation')
out.mkdir(exist_ok=False)
for cpu, (case, producer) in zip((8, 9), PRODUCERS.items(), strict=True):
    command = [
        'taskset', '-c', str(cpu), str(ARCHIVE_PYTHON), '-B', '-m',
        'tools.pipeline_eval.qualification.pilot_confirmation_trial', '--case', case,
    ]
    env = {**os.environ, **SINGLE_THREAD, 'PYTHONPATH': f'{producer.root}:{REPO}'}
    for sample, flags in (('trial', []), ('alternate', ['--holdout'])):
        subprocess.run(
            [*command, *flags, '--out', str(out / f'{case}-{sample}.json.gz')], env=env, check=True,
        )
    subprocess.run(
        [*command, '--audit-exclusion', '--out', str(out / f'{case}-exclusion.json')], env=env, check=True,
    )
write_predictions(out)
PY
```

Six component tests cover exact and rolled synthetic pilots on both edges, fixed fractional epoch and CFO, wrong epoch and frequency, Gaussian noise, absent energy, candidate order, and the input layout. The five archived IQ reader tests also passed. [Qualification runner](../../../tools/pipeline_eval/qualification/pilot_confirmation_trial.py) · [Component tests](../../../tests/pipeline_eval/test_pilot_confirmation.py)
