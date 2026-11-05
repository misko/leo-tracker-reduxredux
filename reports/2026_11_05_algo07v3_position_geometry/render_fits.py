"""Verify complete-fit benchmark bindings and plot all alternating observations."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def main(path):
    out = Path(__file__).resolve().parent
    data = json.loads(path.read_bytes())
    assert data['exact'] and len(data['rows']) == 12
    assert data['affinity'] == [4] and data['blas_threads'] == 1
    for name, sha in data['bindings'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name
    for arm in ('c0', 'fitted_c'):
        rows = [r for r in data['rows'] if r['arm'] == arm]
        assert [r['side'] for r in rows] == [
            'baseline', 'candidate', 'candidate', 'baseline', 'baseline', 'candidate']
        assert all(r['signature'] == rows[0]['signature'] for r in rows)
    tests = path.with_name('benchmark-tests.xml')
    suites = list(ET.parse(tests).getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == 4
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('failures', 'errors', 'skipped'))
    (out / 'complete-fit-pairs.json').write_bytes(path.read_bytes())
    (out / 'benchmark-tests.xml').write_bytes(tests.read_bytes())
    means = data['means']
    reductions = {arm: 100 * (1 - row['candidate']['seconds'] / row['baseline']['seconds'])
                  for arm, row in means.items()}

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    colors = ['#777777', '#3465a4']
    for ax, arm in zip(axes, ('c0', 'fitted_c'), strict=True):
        for i, side in enumerate(('baseline', 'candidate')):
            values = [r['seconds'] for r in data['rows'] if r['side'] == side and r['arm'] == arm]
            bars = ax.bar(np.arange(3) + (i - .5) * .36, values,
                          width=.36, color=colors[i], label=side)
            ax.bar_label(bars, fmt='%.3f', padding=3)
        ax.set(title=f'{arm} · mean {reductions[arm]:.2f}% lower',
               xticks=np.arange(3),
               xticklabels=['Baseline first', 'Candidate first', 'Baseline first'],
               ylabel='Five-round prepared position fit (seconds)', ylim=(0, 2.5))
        ax.legend()
    fig.suptitle('DS26-0002 · exact full fit, phase history, state and final calculation')
    fig.text(.5, .02, 'One CPU / one BLAS thread · new scan context per fit outside timer · '
             'excludes discovery, recovery and publication', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, .94))
    fig.savefig(out / 'complete-fits.png', dpi=160)
    plt.close(fig)
    print(json.dumps(dict(means=means, reductions_percent=reductions), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    main(parser.parse_args().input)
