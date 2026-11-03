import copy
import unittest

from additional_fit import validate_export


class ExportBindingTests(unittest.TestCase):
    def setUp(self):
        self.capture=dict(session_id='scan-A',manifest_sha256='capture-hash')
        self.receipt=dict(index=2,exit_code=0,source_sha256='exporter')
        self.validated=dict(index=2,source_sha256='exporter',input=dict(self.capture))

    def test_exact_binding(self):
        self.assertEqual(validate_export(2,self.capture,self.receipt,self.validated,'exporter'),self.capture)

    def test_each_binding_is_required(self):
        for target,key,value in [('receipt','index',3),('receipt','exit_code',124),
                                 ('receipt','source_sha256','other'),('validated','index',3),
                                 ('validated','source_sha256','other'),('input','session_id','scan-B'),
                                 ('input','manifest_sha256','different-capture')]:
            receipt=copy.deepcopy(self.receipt)
            validated=copy.deepcopy(self.validated)
            mapping={'receipt':receipt,'validated':validated,'input':validated['input']}
            mapping[target][key]=value
            with self.subTest(target=target,key=key),self.assertRaises(AssertionError):
                validate_export(2,self.capture,receipt,validated,'exporter')


if __name__=='__main__':
    unittest.main()
