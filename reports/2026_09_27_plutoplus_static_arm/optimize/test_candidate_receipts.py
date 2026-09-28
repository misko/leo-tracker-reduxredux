#!/usr/bin/env python3
"""Focused tests for qualified-reference and contention-summary rejection."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


HERE=Path(__file__).resolve().parent


def load(name: str):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+".py"))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PREP=load("prepare_worker_reference")
SUMMARY=load("summarize_candidate_phase")


class CandidateReceiptTests(unittest.TestCase):
    candidate="candidate"

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="candidate-receipts-")
        self.base=Path(self.temp.name)
        self.optimize=self.base/"optimize"
        self.concurrent=self.base/"concurrent"
        self.concurrent.mkdir(parents=True)
        self.case={"case_id":"case-a"}
        (self.concurrent/"selected-cases.json").write_text(json.dumps([self.case]))
        self.source=self.optimize/"work"/self.candidate/"arm-check"
        self.source.mkdir(parents=True)
        binary=self.optimize/"work"/self.candidate/"arm"
        binary.write_bytes(b"qualified binary")
        self.digest=hashlib.sha256(binary.read_bytes()).hexdigest()
        (self.optimize/"work"/self.candidate/"arm.build.json").write_text(
            json.dumps({"binary_sha256":self.digest}))
        (self.source/"manifest.json").write_text(json.dumps({"sha256":self.digest}))
        (self.source/"completion.json").write_text(json.dumps({"complete":True,"passed":True}))
        (self.source/"assessments.json").write_text(json.dumps([{"case_id":"case-a","passed":True}]))
        (self.source/"case-a.json").write_text(json.dumps({"method":self.candidate}))

    def tearDown(self):
        self.temp.cleanup()

    def test_reference_rejects_bad_candidate_science_and_binary(self):
        with self.assertRaises(ValueError): PREP.prepare_reference("bad-name",self.optimize)
        (self.source/"completion.json").write_text(json.dumps({"complete":True,"passed":False}))
        with self.assertRaisesRegex(ValueError,"scientific"):
            PREP.prepare_reference(self.candidate,self.optimize)
        self.assertFalse((self.optimize/"persistent").exists())
        (self.source/"completion.json").write_text(json.dumps({"complete":True,"passed":True}))
        (self.optimize/"work"/self.candidate/"arm.build.json").write_text(json.dumps({"binary_sha256":"bad"}))
        with self.assertRaisesRegex(ValueError,"binary"):
            PREP.prepare_reference(self.candidate,self.optimize)
        self.assertFalse((self.optimize/"persistent").exists())

    def test_reference_rejects_unqualified_selected_case_without_artifact(self):
        (self.source/"case-a.json").write_text(json.dumps({"method":"other"}))
        with self.assertRaisesRegex(ValueError,"case not qualified"):
            PREP.prepare_reference(self.candidate,self.optimize)
        self.assertFalse((self.optimize/"persistent").exists())

    def test_phase_rejects_invalid_and_counts_idle_excluding_guest(self):
        reference=self.optimize/"persistent"/"references"/self.candidate
        reference.mkdir(parents=True)
        (reference/"qualification.json").write_text(json.dumps({
            "candidate":self.candidate,"original_D_scientific_gate_passed":True}))
        phase=self.base/"phase";phase.mkdir()
        invalid={"run":{"candidate":self.candidate},"validity":{"passed":False}}
        original=SUMMARY.summarize_phase
        try:
            SUMMARY.summarize_phase=lambda _phase,_reference:invalid
            with self.assertRaisesRegex(RuntimeError,"invalid phase"):
                SUMMARY.summarize_candidate_phase(phase,self.candidate,self.optimize)
            self.assertFalse((phase/"summary.json").exists())
            valid={"run":{"candidate":self.candidate},"validity":{"passed":True},
                   "cpu":{"capture_overlap":{"cores":{"0":{"user":30,"idle":50,"iowait":20,
                   "guest":10,"guest_nice":0}}}},"glrt":{"parity":{},"capture_overlap":{}}}
            SUMMARY.summarize_phase=lambda _phase,_reference:valid
            result=SUMMARY.summarize_candidate_phase(phase,self.candidate,self.optimize)
        finally:
            SUMMARY.summarize_phase=original
        self.assertEqual(result["capture_overlap_busy_percent"]["0"],30.0)
        self.assertEqual(result["cpu0_headroom_percent"],70.0)
        self.assertTrue(result["at_least_40_percent_headroom"])


if __name__=="__main__":
    unittest.main()
