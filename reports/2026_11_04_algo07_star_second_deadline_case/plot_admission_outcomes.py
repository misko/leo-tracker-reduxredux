"""Plot recorded ALGO03 admission outcomes, without inferring full equivalence."""
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

ROOT = Path(__file__).resolve().parent
SOURCES = [('DS26-0170', 'diagnostic-summary.json'),
           ('DS26-0102', 'ds26-0102-optimized-diagnostic-summary.json'),
           ('DS26-0259', 'ds26-0259-optimized-diagnostic-summary.json')]
STYLE = {
    'RF_qualified': ('#b9e2bd', 'RF qualified'),
    'RF_rejected': ('#f3cf99', 'RF rejected'),
    'unstable_identity': ('#c9d7e4', 'Unstable ID'),
    'ambiguous_identity': ('#c9d7e4', 'Ambiguous ID'),
    'prediction_mismatch': ('#c9d7e4', 'Prediction mismatch'),
    'discovery_budget_exhausted': ('#e7e7e7', 'Not evaluated'),
}
fig, axes = plt.subplots(3, 1, figsize=(14, 7.6), constrained_layout=True)
bindings, counts = [], []
for ax, (label, filename) in zip(axes, SOURCES, strict=True):
    source = ROOT / filename
    data = json.loads(source.read_text())
    bindings.append(dict(path=filename, sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    reference = data['sides']['reference']['attempts']
    candidate = data['sides']['candidate']['attempts']
    assert [(a['track_id'], a['points']) for a in reference] == [
        (a['track_id'], a['points']) for a in candidate]
    for y, (side, attempts) in enumerate((('Reference', reference), ('ALGO07*', candidate))):
        admitted = sum(a['status'] != 'discovery_budget_exhausted' for a in attempts)
        counts.append(dict(case=label, side=side, admitted=admitted, targets=len(attempts)))
        for x, attempt in enumerate(attempts):
            color, caption = STYLE[attempt['status']]
            differs = reference[x]['status'] != candidate[x]['status']
            ax.add_patch(Rectangle((x - .47, y - .40), .94, .8, facecolor=color,
                                   edgecolor='#a64122' if differs else 'white',
                                   linewidth=2 if differs else 1))
            ax.text(x, y, f"{caption}\n{attempt['points']} points", ha='center',
                    va='center', fontsize=8.5)
    ax.set(xlim=(-.5, 7.5), ylim=(1.5, -.5), yticks=[0, 1],
           yticklabels=['Reference', 'ALGO07*'], xticks=range(8),
           xticklabels=[f'Target {i}' for i in range(8)])
    ax.set_title(f'{label}: {counts[-2]["admitted"]} versus {counts[-1]["admitted"]} '
                 'targets evaluated', loc='left', fontsize=12)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
fig.suptitle('Strict DS26 failures: unchanged ALGO03 admits different work under wall-clock limits',
             fontsize=14)
fig.supxlabel(
    'Red outline: different recorded outcome. Target order is within each scan.\n'
    'RF qualification is not final position acceptance. Selected results match in limited\n'
    'diagnostics; full intermediate parity fails.', fontsize=10)
output = ROOT / 'admission-outcomes.png'
fig.savefig(output, dpi=160)
plt.close(fig)
(ROOT / 'admission-outcomes-evidence.json').write_text(json.dumps(dict(
    kind='algo07-star-recorded-admission-figure', inputs=bindings, counts=counts,
    figure_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    full_scientific_equivalence=False), indent=2) + '\n')
print(json.dumps(counts))
