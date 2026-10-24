import unittest
from export_publication import compact

class CompactPublicationTest(unittest.TestCase):
    def test_failed_candidate_and_fallback_remain_visible(self):
        source={'case':'DS24-0001','status':'complete','methods':{'native':{
            'accepted':True,'candidate_accepted':False,'fallback':'baseline',
            'arms':{'c0':{'endpoint_latlon':[1,2],'state':{'huge':[0]*20},'history':[1]*20,
                'gates':{'tracks':[{'compatible':True},{'compatible':False,'component':'bad','observation_ids':['a']}]}}},
            'coverage':{'c0':{'associated':2,'total_GLRT':3,'accepted_observation_ids':['b','a']}}}}}
        result=compact(source)['methods']['native']
        self.assertFalse(result['candidate_accepted']);self.assertEqual(result['fallback'],'baseline')
        self.assertNotIn('state',result['arms']['c0']);self.assertNotIn('history',result['arms']['c0'])
        self.assertEqual(result['arms']['c0']['curved_gates']['failed'],[{'compatible':False,'component':'bad'}])
        self.assertEqual(result['coverage']['c0']['accepted_observation_ids_count'],2)
        source['methods']['native']['coverage']['c0']['accepted_observation_ids'].reverse()
        self.assertEqual(result['coverage'],compact(source)['methods']['native']['coverage'])

if __name__=='__main__':unittest.main()
