"""Scientific receipt checks for the bounded experiment, not production tests."""
import hashlib
import math
import unittest
from pathlib import Path
from prototype import OUT,PRIOR,INPUT,CASES,ARMS,read,age_penalty

class ExperimentTests(unittest.TestCase):
    def test_prior_odds_and_cutoff(self):
        self.assertAlmostEqual(math.exp(-.5*(age_penalty(48,'linear24')-age_penalty(24,'linear24'))),.5)
        self.assertEqual(age_penalty(48,'hard48'),0)
        self.assertTrue(math.isinf(age_penalty(48.001,'hard48')))
        self.assertEqual(age_penalty(48,'grace48'),0)
        self.assertEqual(age_penalty(60,'grace48'),1)
        for invalid in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):age_penalty(invalid,'none')

    def test_frozen_inputs(self):
        protocol=read(OUT/'protocol.json')
        for c in CASES:
            for path,digest in protocol['cases'][c]['hashes'].items():
                self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(),digest)

    def test_matching_trials_and_native_evidence(self):
        protocol=read(OUT/'protocol.json');count=0
        for case in CASES:
            files=list((OUT/case).glob('*-w*.json'));self.assertEqual(len(files),4*len(protocol['cases'][case]['nominees']))
            reference=None
            for path in files:
                trial=read(path);self.assertEqual({(r['arm'],r['start']) for r in trial['rows']},{(a,s) for a in ARMS for s in ('published','family_omitted')})
                for row in trial['rows']:
                    ids=[o for t in row['tracks'] for o in t['observation_ids']]
                    self.assertEqual(len(ids),len(set(ids)));self.assertEqual(len(ids),row['active_points'])
                    if reference is None:reference=set(ids)
                    self.assertEqual(set(ids),reference)
                    if row['qualified']:
                        self.assertTrue(row['phase_closed'] and row['optimizer_success'] and row['all_gates_pass'])
                        self.assertEqual(row['lost_ids'],[])
                        self.assertTrue(all(v['all_pass'] for v in row['exact']))
                    count+=1
        self.assertEqual(count,144)

    def test_age_scores_are_causal_and_have_no_new_continuous_fits(self):
        provenance=read(OUT/'provenance.json');summary=read(OUT/'summary.json')
        for case in CASES:
            cutoff=read(INPUT/(case+'.json'))['scan_receipt']['cutoff_utc_ns']
            for e in provenance[case]['catalogue'].values():
                self.assertLessEqual(e['epoch'],cutoff);self.assertLessEqual(e['collected'],cutoff)
                self.assertGreaterEqual(e['age_h'],0);self.assertLessEqual(e['age_h'],72)
            for a in ARMS:
                rows=[r for r in summary['selected'] if r['case']==case and r['arm']==a and r['constrained']]
                control=next(r for r in rows if r['policy']=='none')
                for row in rows:
                    if row['norad']==control['norad']:
                        self.assertEqual(row['error_km'],control['error_km'])

    def test_fallback_prior_changes_only_target_width(self):
        for case,n in [('DS26-0070',63571),('DS26-0251',58787)]:
            control=read(OUT/case/f'{n}-w1-constrained.json')['rows']
            for factor in (2,4):
                rows=read(OUT/case/f'fallback-prior-{n}-x{factor}.json')['rows']
                self.assertEqual(len(rows),4)
                for row in rows:
                    base=next(r for r in control if r['arm']==row['arm'] and r['start']==row['start'])
                    self.assertEqual(row['active_points'],base['active_points'])
                    original={r['norad']:r['phase_sigma_s'] for r in base['parameters']}
                    for param in row['parameters']:
                        self.assertAlmostEqual(param['phase_sigma_s'],original[param['norad']]*(factor if param['norad']==n else 1))

if __name__=='__main__':unittest.main()
