import copy
import unittest
from audit_campaign import check_refinement,check_assignments,check_position


class CampaignAuditTests(unittest.TestCase):
    def position_fixture(self):
        stages=['roof']+[f'probe-{i:02d}' for i in range(32)]+[f'search-{i}' for i in range(3)]
        stages += [f'{kind}-transfer-{i}' for kind in ('roof','best','joint') for i in range(2)]
        stages += [f'gradient-{h:g}-{axis}-{sign}' for h in (.05,.1) for axis in (0,1) for sign in (-1,1)]
        records=[dict(stage=s,objective=1.,point_km=[0.,0.],coefficient=0.,success=True,
                      fixed_location=not s.startswith(('search-','joint-transfer-'))) for s in stages]
        gradients={str(h):dict(gradient_per_km=[0.,0.],all_converged=True) for h in (.05,.1)}
        result=dict(records=records,best_found=records[0],roof=records[0],radius_m=0.,boundary=False,
                    ambiguous=False,finite_difference_gradient=gradients)
        meta=dict(method='alternatives',ranking='support',fraction=1.,fixed_observation_original_rows=[1],retained_windows=1)
        return dict(signature=dict(inputs=meta,probe_budget_s=8.,search_budget_s=20.),
                    arms={a:copy.deepcopy(result) for a in ('fitted-c','zero-c')})

    def test_complete_matched_position_design_required(self):
        d=self.position_fixture();check_position(d,'support',1.)
        d['arms']['zero-c']['records'].pop()
        with self.assertRaisesRegex(ValueError,'stages'):check_position(d,'support',1.)
        d=self.position_fixture();d['arms']['zero-c']['records'][1]['stage']='roof'
        with self.assertRaisesRegex(ValueError,'stages'):check_position(d,'support',1.)

    def test_changed_budgets_and_rf_probe_coordinates_rejected(self):
        d=self.position_fixture();d['signature']['search_budget_s']=10.
        with self.assertRaisesRegex(ValueError,'budgets'):check_position(d,'support',1.)
        d=self.position_fixture();d['arms']['zero-c']['records'][1]['point_km']=[.1,0.]
        with self.assertRaisesRegex(ValueError,'different fixed'):check_position(d,'support',1.)

    def test_gradient_values_and_convergence_checked_against_records(self):
        d=self.position_fixture()
        d['arms']['fitted-c']['finite_difference_gradient']['0.05']['gradient_per_km']=[1.,0.]
        with self.assertRaisesRegex(ValueError,'differs from saved'):check_position(d,'support',1.)
        d=self.position_fixture();d['arms']['fitted-c']['records'][-1]['success']=False
        with self.assertRaisesRegex(ValueError,'convergence flag'):check_position(d,'support',1.)

    def refinement_fixture(self):
        rows=[dict(candidate_id=str(i),row_index=i,probe_key=[0],original_hz=10,original_margin=.1) for i in range(2)]
        original=dict(records=copy.deepcopy(rows),summary=dict(passing_windows=1))
        for i,row in enumerate(rows):row.update(refinement=dict(status='refined',margin=.1+i),output_hz=10)
        return original,dict(records=rows,summary=dict(status='complete'),top_rows=[1])

    def test_wrong_top_candidate_rejected(self):
        original,refined=self.refinement_fixture();check_refinement(original,refined)
        refined['top_rows']=[0]
        with self.assertRaisesRegex(ValueError,'highest refined'):check_refinement(original,refined)

    def test_failed_refinement_cannot_silently_change_frequency(self):
        original,refined=self.refinement_fixture();refined['records'][0].update(refinement={'status':'failed'},output_hz=11)
        with self.assertRaisesRegex(ValueError,'retain original'):check_refinement(original,refined)

    def test_two_candidates_must_not_be_counted_as_two_windows(self):
        original={'records':[dict(group_id='x'),dict(group_id='x')],'summary':dict(passing_windows=2)}
        final=dict(assigned=2,unassigned=0,denominator=2,coverage=1.,objective=-8.,satellites=1,
                   assignments=[dict(original_row_index=i,catalog_number=10,residual_hz=0) for i in range(2)])
        selection={'arms':{a:{m:dict(final=final) for m in ('greedy','replacement','alternatives')} for a in ('fitted-c','zero-c')}}
        with self.assertRaisesRegex(ValueError,'double counting'):check_assignments(selection,original)
