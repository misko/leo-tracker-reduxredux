"""Report-owned tests; no hardware, database, QNAP, or new fitting."""
import json
import csv
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import zipfile
import numpy as np
from reference_math import ALIAS_HZ, wrap, zero_sum_basis, glrt_spectrum, single_window_terms, timing_penalty


def test_alias_invariance():
    x = np.array([-3.4e5, -20., 0., 333.])
    np.testing.assert_allclose(wrap(x+3*ALIAS_HZ), wrap(x), atol=1e-9)
    assert wrap(ALIAS_HZ/2) == -ALIAS_HZ/2


def test_basis_gauge():
    for k in (1, 2, 30):
        b = zero_sum_basis(k)
        np.testing.assert_allclose(b.sum(axis=0), 0, atol=1e-14)
        np.testing.assert_allclose(b.T@b, np.eye(k-1), atol=1e-14)


def test_glrt_tone_and_scale():
    frequency = 17*ALIAS_HZ/4096
    z = np.exp(2j*np.pi*frequency*4.4e-6*np.arange(64))[None, :]*np.array([1, 2j])[:, None]
    _, _, f, score = glrt_spectrum(z)
    assert abs(f-frequency) < 1e-9 and abs(score-1) < 1e-12
    np.testing.assert_allclose(glrt_spectrum(z*7)[1], glrt_spectrum(z)[1], atol=1e-14)


def test_responsibilities_and_gradient():
    y = np.array([20., 210., 12.]); mu = np.array([[0., 30., 1700.], [0., 900., -20.], [1., 2., 3.]])
    v = np.ones(mu.shape, bool); v[2] = False
    log_l, z, clutter, grad = single_window_terms(y, mu, v)
    np.testing.assert_allclose(z.sum(axis=1)+clutter, 1., atol=1e-14)
    assert np.all(z[2] == 0) and np.isfinite(log_l).all()
    h = 1e-2
    for i, j in np.ndindex(mu.shape):
        delta = np.zeros_like(mu); delta[i, j] = h
        plus = -single_window_terms(y, mu+delta, v)[0].sum()
        minus = -single_window_terms(y, mu-delta, v)[0].sum()
        np.testing.assert_allclose((plus-minus)/(2*h), grad[i, j], atol=1e-9)


def test_frozen_full_scan_objective():
    fixture = json.loads((Path(__file__).parent/'numerical-check.json').read_text())
    assert fixture['scan'] == 'N01' and fixture['windows'] == 2444
    assert fixture['maximum_objective_error'] < 1e-7
    assert fixture['maximum_posterior_rms_error_hz'] < 1e-7


def test_prior_not_hard_bound():
    assert timing_penalty(0., [1., -1.]) > 40
    assert np.isfinite(timing_penalty(0., [1., -1.]))


def test_report_links_and_equations():
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.targets = []
            self.ids = set()

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if 'id' in attrs:
                self.ids.add(attrs['id'])
            if tag in {'a', 'img'}:
                self.targets.append(attrs.get('href', attrs.get('src', '')))

    folder = Path(__file__).parent
    html = (folder/'report.html').read_text()
    markdown = (folder/'report.md').read_text()
    parser = Links()
    parser.feed(html)
    assert 'V16MATHPLACEHOLDER' not in html
    assert html.count(r'\[') >= markdown.count(r'\[') > 20
    for target in parser.targets:
        if target.startswith('#'):
            assert target[1:] in parser.ids
        elif target and '://' not in target:
            assert (folder/target).is_file(), target


def test_cohort_and_reproduction_scope():
    folder = Path(__file__).parent
    with (folder/'cohort.csv').open() as stream:
        cohort = list(csv.DictReader(stream))
    assert len(cohort) == 16
    assert {float(row['sample_rate_hz']) for row in cohort} == {2_500_000.}
    assert sum(int(row['passing_windows']) for row in cohort) == 46_775
    assert sum(int(row['associated_windows']) for row in cohort) == 42_610
    assert sum(int(row['passing_candidates']) for row in cohort) == 134_835
    checks = json.loads((folder/'numerical-check.json').read_text())['cases']
    assert {(row['scan'], row['arm']) for row in checks} == {
        (f'N{i:02}', arm) for i in range(1, 17) for arm in ('fitted-c', 'zero-c')}
    assert all(row['objective_error'] < 1e-7 for row in checks)
    assert all(row['posterior_rms_error_hz'] < 1e-7 for row in checks)


def test_source_appendix_integrity():
    folder = Path(__file__).parent
    inventory = json.loads((folder/'implementation-sources.json').read_text())
    with zipfile.ZipFile(folder/'implementation-sources.zip') as archive:
        assert set(archive.namelist()) == {row['member'] for row in inventory}
        for row in inventory:
            assert hashlib.sha256(archive.read(row['member'])).hexdigest() == row['sha256']
