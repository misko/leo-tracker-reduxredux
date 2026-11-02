"""Publication must reject stale audit bindings and nonconverged controls."""
import copy,unittest
from population_final_review import check_record

class FinalReceiptTests(unittest.TestCase):
    def fixture(self):
        baseline={a:dict(error_m=3.,objective=20.,associated=4,selected=None) for a in ('c0','fitted_c')}
        record=dict(case='FAKE',identities=['recording'],input_sha256='input',baseline=baseline,selected=None)
        worker=dict(case='FAKE',protocol_sha256='protocol',source_input_sha256='input',baseline=baseline)
        receipt=dict(case='FAKE',protocol_sha256='protocol',input_sha256='input',worker_receipt_sha256='worker',final_accepted=False,status='passed')
        row=dict(case='FAKE',identities=['recording'],baseline=baseline,accepted=False,final_audit=receipt,
            selected_output={a:dict(baseline[a],source='exact_saved_ALGO07') for a in baseline})
        kw=dict(protocol_hash='protocol',input_hash='input',worker_hash='worker',threshold=2.)
        return record,worker,row,receipt,kw

    def test_stale_worker_receipt_is_not_publishable(self):
        record,worker,row,receipt,kw=self.fixture()
        self.assertEqual(check_record(record,worker,row,receipt,**kw),[])
        kw['worker_hash']='newer_worker'
        self.assertIn('audit references stale worker receipt',check_record(record,worker,row,receipt,**kw))

    def test_rejected_case_must_keep_exact_saved_fallback(self):
        record,worker,row,receipt,kw=self.fixture()
        row['selected_output']['c0']['error_m']=0.
        self.assertIn('c0 fallback not exact saved ALGO07',check_record(record,worker,row,receipt,**kw))

    def test_candidate_cannot_replace_baseline_with_nonclosed_control(self):
        record,worker,row,receipt,kw=self.fixture()
        native=dict(all_native_union_sha256='ids',all_native_count=4,native_counts=dict(curved=4),fitted_owners_sha256='owners')
        candidate=dict(native,objective=10.,error_m=2.,optimizer_success=True,phase_closed=True,
            all_gates_pass=True,native_ids_preserved=True,all_native_IDs_preserved=True,all_fitted_owners_preserved=True,
            incumbent_lost=0,unrelated_reassigned=0,mixture_phase_boundary_masses=[],exact_orbit_checks=[dict(all_pass=True)])
        row.update(accepted=True,candidate={a:dict(candidate) for a in ('c0','fitted_c')},
            control={a:dict(candidate,objective=15.,phase_closed=False) for a in ('c0','fitted_c')},
            objective_gains={a:dict(vs_matched_control=5.,vs_saved_baseline=10.) for a in ('c0','fitted_c')},
            selected_output={a:dict(error_m=2.,objective=10.,associated=4,source='SD4_half_candidate') for a in ('c0','fitted_c')})
        receipt.update(final_accepted=True,baseline_native_inventory={a:dict(native) for a in ('c0','fitted_c')})
        issues=check_record(record,worker,row,receipt,**kw)
        self.assertEqual(issues,['c0 matched control not converged','fitted_c matched control not converged'])

if __name__=='__main__':unittest.main()
