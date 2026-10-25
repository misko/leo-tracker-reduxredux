"""Component-owned verification. No new RF, golden changes, or position fits."""
import copy
from pathlib import Path
import tempfile
import unittest

import numpy as np

from common import (ARMS, MODELS, SCALES, SEEDS, digest, load_sealed, read,
    value_digest, verify_bindings, write_new)
from kernel import (build, causal_reference, family_partition, fold_assignment,
    gaussian_score, held_posterior, training_data)
from matched_controls import load_baseline
from policy import decide, job_failures
from run_batch import approved, select_workers


def valid_result(seed, fold):
    result = dict(case='synthetic', seed=seed, fold=fold, status='complete', arms={})
    for arm in ARMS:
        result['arms'][arm] = dict(fits={}, crossover={})
        for model in MODELS:
            result['arms'][arm]['fits'][model] = dict(final_phase_change_s=.001,
                training_final_log_precision_change=1e-6, endpoint_east_north_km=[1., 2.],
                history=[dict(fit=dict(stopped='no_accepted_damped_step'))])
        for predictor in MODELS:
            result['arms'][arm]['crossover'][predictor] = {}
            for endpoint in MODELS:
                score = 2. if endpoint == 'baseline' else 1.
                result['arms'][arm]['crossover'][predictor][endpoint] = dict(
                    phase_refresh_changes_s=[.001], final_log_precision_change=1e-6,
                    scores={str(s): dict(negative_twice_log_density=score, quadratic=score, logdet=0.) for s in SCALES})
    return result


class ScoreTests(unittest.TestCase):
    def test_dense_and_independent_svd_scores(self):
        rng = np.random.default_rng(9)
        raw = rng.normal(size=19)
        uncertainty = rng.normal(size=(19, 6))
        sigma = rng.uniform(.4, 2., 19)
        got = gaussian_score(raw, uncertainty, sigma)
        covariance = np.diag(sigma**2) + uncertainty@uncertainty.T
        dense = raw@np.linalg.solve(covariance, raw) + np.linalg.slogdet(covariance)[1] + 19*np.log(2*np.pi)
        q, s, _ = np.linalg.svd(uncertainty/sigma[:, None], full_matrices=False)
        b = raw/sigma
        quadratic = b@b - np.sum((s*s/(1+s*s))*(q.T@b)**2)
        logdet = 2*np.log(sigma).sum() + np.log1p(s*s).sum()
        self.assertAlmostEqual(got['negative_twice_log_density'], dense, places=10)
        self.assertAlmostEqual(got['quadratic'], quadratic, places=11)
        self.assertAlmostEqual(got['logdet'], logdet, places=11)

    def test_shared_covariance_is_not_family_additive(self):
        raw, u, sigma = np.full(12, 3.), np.ones((12, 1)), np.ones(12)
        joint = gaussian_score(raw, u, sigma)['negative_twice_log_density']
        marginals = sum(gaussian_score(raw[i:i+1], u[i:i+1], sigma[i:i+1])['negative_twice_log_density'] for i in range(12))
        self.assertGreater(marginals-joint, 20.)


class FrozenOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_baseline('DS24-0017')

    def test_exact_randomization_and_disjoint_owner_removal(self):
        for seed in SEEDS:
            partition = family_partition(self.data, seed)
            rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, 17])))
            np.testing.assert_array_equal(partition['permutation'], rng.permutation(partition['active_family_indices']))
            self.assertEqual(partition, family_partition(self.data, seed))
            groups = partition['folds']
            self.assertEqual(len(set().union(*map(set, groups))), sum(map(len, groups)))
            for held in groups:
                train = training_data(self.data, held)
                arm_ids = []
                for arm in ARMS:
                    p = build(train, arm, causal_reference(train, held), 'baseline')
                    self.assertFalse(np.isin(np.asarray(p.labels)[p.flat_labels[p.keep]], held).any())
                    self.assertFalse(any(e['candidate_index'] in held for e in train['entries']))
                    ids = np.asarray([oid for i in p.members for oid in p.scan.tracks[i]['observation_ids']])
                    train_ids = ids[p.keep].tolist() + [oid for e in train['entries'] for oid in e['observation_ids']]
                    held_ids = ids[np.asarray(self.data['keep']) & np.isin(np.asarray(p.labels)[p.flat_labels], held)].tolist()
                    held_ids += [oid for e in self.data['entries'] if e['candidate_index'] in held for oid in e['observation_ids']]
                    self.assertFalse(set(train_ids) & set(held_ids))
                    self.assertEqual(len(train_ids + held_ids), len(set(train_ids + held_ids)))
                    arm_ids.append((train_ids, held_ids))
                self.assertEqual(arm_ids[0], arm_ids[1])

    def test_held_cfo_redaction_cannot_change_training(self):
        held = fold_assignment(self.data, SEEDS[0])[0]
        train = training_data(self.data, held)
        for arm in ARMS:
            for model in MODELS:
                p = build(train, arm, causal_reference(train, held), model)
                x = np.array([.2, -.3])
                before = p.calculate(x)
                held_posterior(p, p.curved_calculate(x), train, held)
                changed = dict(train)
                changed['scan'] = copy.copy(train['scan'])
                changed['scan'].tracks = copy.deepcopy(train['scan'].tracks)
                tracks = {i for i, r in zip(p.members, p.rows, strict=True) if r['candidate_index'] in held}
                tracks.update(e['track_index'] for e in self.data['entries'] if e['candidate_index'] in held)
                for i in tracks:
                    changed['scan'].tracks[i]['values'] = np.asarray(changed['scan'].tracks[i]['values']) + 12345.
                q = build(changed, arm, causal_reference(changed, held), model)
                after = q.calculate(x)
                for key in ('coefficient', 'noise_precision', 'negative_twice_elbo'):
                    np.testing.assert_array_equal(before[key], after[key])
                np.testing.assert_array_equal(p.residual(x), q.residual(x))


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.results = [valid_result(seed, fold) for seed in SEEDS for fold in range(3)]
        self.full = dict(eligible=True, original_adopted=True, original_paired_gates_pass=True,
            baseline_pair={a: [0., 0.] for a in ARMS}, candidate_pair={a: [1., 2.] for a in ARMS},
            baseline_binding=dict(path='baseline', sha256='baseline'), candidate_binding=dict(path='rx1', sha256='rx1'))

    def test_all_conditions_accept_one_exact_pair(self):
        decision = decide('synthetic', self.results, self.full)
        self.assertTrue(decision['adopted'])
        self.assertEqual(len(decision['aggregate_gains']), 24)
        self.assertEqual(decision['endpoint_pair'], self.full['candidate_pair'])

    def test_phase_gamma_budget_timeout_and_original_gate_fallback(self):
        interventions = [
            lambda r, f: r[0]['arms']['c0']['fits']['baseline'].update(final_phase_change_s=.01001),
            lambda r, f: r[0]['arms']['fitted_c']['fits']['sharedRF50'].update(training_final_log_precision_change=1.0001e-5),
            lambda r, f: r[0]['arms']['c0']['crossover']['baseline']['sharedRF50'].update(final_log_precision_change=1.0001e-5),
            lambda r, f: r[0]['arms']['c0']['crossover']['baseline']['sharedRF50'].update(phase_refresh_changes_s=[.01001]),
            lambda r, f: r[0]['arms']['c0']['fits']['baseline']['history'][-1]['fit'].update(stopped='iteration_budget'),
            lambda r, f: r[0].update(status='timeout'),
            lambda r, f: f.update(original_adopted=False),
            lambda r, f: f.update(eligible=False),
            lambda r, f: f.update(original_paired_gates_pass=False),
            lambda r, f: r.pop(),
        ]
        for intervention in interventions:
            results, full = copy.deepcopy(self.results), copy.deepcopy(self.full)
            intervention(results, full)
            decision = decide('synthetic', results, full)
            self.assertFalse(decision['adopted'])
            self.assertEqual(decision['endpoint_pair'], full['baseline_pair'])
            self.assertEqual(decision['exact_pair_source_binding'], full['baseline_binding'])

    def test_nonpositive_one_arm_one_scale_forces_pair_fallback(self):
        for result in self.results[:3]:
            result['arms']['c0']['crossover']['baseline']['baseline']['scores'][str(SCALES[0])]['negative_twice_log_density'] = 1.
        self.assertFalse(decide('synthetic', self.results, self.full)['adopted'])

    def test_nonfinite_or_duplicate_job_cannot_adopt(self):
        changed = copy.deepcopy(self.results)
        changed[0]['arms']['c0']['crossover']['baseline']['baseline']['scores'][str(SCALES[0])]['quadratic'] = float('nan')
        self.assertFalse(decide('synthetic', changed, self.full)['adopted'])
        self.assertFalse(decide('synthetic', self.results + [self.results[0]], self.full)['adopted'])

    def test_fold_majority_is_not_a_requirement(self):
        for fold, gain in enumerate((-1., -1., 3.)):
            for result in [r for r in self.results if r['fold'] == fold]:
                for analysis in result['arms'].values():
                    for predictor in analysis['crossover'].values():
                        for scale in SCALES:
                            predictor['baseline']['scores'][str(scale)]['negative_twice_log_density'] = 1. + gain
        self.assertTrue(decide('synthetic', self.results, self.full)['adopted'])


class DriverTests(unittest.TestCase):
    def test_tampered_protocol_seal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_new(root/'protocol.json', dict(original=True))
            write_new(root/'freeze_seal.json', dict(protocol_sha256=digest(root/'protocol.json')))
            (root/'protocol.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'protocol seal mismatch'):
                load_sealed(root)

    def test_tampered_binding_rejected_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'input.json'
            write_new(path, dict(value=1))
            sealed = dict(path=str(path), sha256=digest(path))
            verify_bindings([sealed])
            with self.assertRaises(FileExistsError):
                write_new(path, dict(value=2))
            path.write_text('{}')
            with self.assertRaises(ValueError):
                verify_bindings([sealed])

    def test_approval_is_bound_to_exact_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'approval.json'
            write_new(path, dict(approved=True, movement_protocol_sha256='abc'))
            approved(path, 'abc')
            with self.assertRaises(ValueError):
                approved(path, 'different')

    def test_resource_rule_uses_bytes_and_declared_cpu_capacity(self):
        self.assertEqual(select_workers(1000, dict(allocated_cpu_capacity=8, memory_available_bytes=10**9)), 6)
        self.assertEqual(select_workers(1000, dict(allocated_cpu_capacity=7, memory_available_bytes=10**9)), 2)
        self.assertEqual(select_workers(10**8, dict(allocated_cpu_capacity=8, memory_available_bytes=10**9)), 2)


if __name__ == '__main__':
    unittest.main()
