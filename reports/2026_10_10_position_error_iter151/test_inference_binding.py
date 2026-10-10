import unittest
from inference_binding import projected_binding,MODEL_FIELDS,PHYSICAL_FIELDS

class BindingTests(unittest.TestCase):
    def fixture(self):
        member=dict(label='DS16-020',membership={'session_id':'s'},binding={'session_id':'s','document_path':'clean'})
        model={key:key for key in MODEL_FIELDS};model['session_id']='s'
        expected={key:key for key in PHYSICAL_FIELDS};expected.update(input_digest=model['input_manifest_sha256'],evidence_digest=model['evidence_sha256'],bank_signature=model['bank_signature'])
        document={key:model[key] for key in ('session_id','input_manifest_sha256','analysis_manifest_sha256','evidence_sha256')}
        return member,dict(member={'session_id':'s'},model_identity=model,reference='forbidden'),dict(status='complete',label='DS16-020',input_binding=expected,error_km=999),document
    def test_only_inference_projection(self):
        args=self.fixture();binding=projected_binding(*args)
        self.assertEqual(set(binding['model_identity']),set(MODEL_FIELDS))
        self.assertEqual(set(binding['expected_input_binding']),set(PHYSICAL_FIELDS))
        self.assertNotIn('reference',str(binding));self.assertNotIn('error_km',str(binding))
    def test_missing_authority_and_wrong_session(self):
        args=list(self.fixture());args[2]['input_binding']['observation_order_signature']=''
        with self.assertRaises(ValueError):projected_binding(*args)
        args=list(self.fixture());args[1]['member']['session_id']='wrong'
        with self.assertRaises(ValueError):projected_binding(*args)

if __name__=='__main__':unittest.main()
