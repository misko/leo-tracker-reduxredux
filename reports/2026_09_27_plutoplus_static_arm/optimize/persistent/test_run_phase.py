#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_phase


class FakeRemote:
    def __init__(self):
        self.calls = []
        self.mask = "3"

    def __call__(self, command, timeout=10, input_data=None):
        self.calls.append(command)
        if command == "sed -n '/eth0/p' /proc/interrupts":
            return b" 35: 1 2 eth0\n"
        if command == "cat /proc/irq/35/smp_affinity":
            return (self.mask + "\n").encode()
        if command == "cat /proc/irq/35/effective_affinity_list":
            return ("1\n" if self.mask == "2" else "0-1\n").encode()
        if command.startswith("echo "):
            self.mask = command.split()[1]
            return b""
        raise AssertionError(command)


class PhaseTests(unittest.TestCase):
    def test_validation_rejects_unsafe_name_before_receipt_read(self):
        args = argparse.Namespace(name="../bad", candidate="rankconversion", jobs=1,
            period=120, seconds=5, capture_seconds=5, capture_rate=2_500_000,
            recorded_arrivals=False)
        with self.assertRaisesRegex(ValueError, "phase name"):
            run_phase.validate(args)

    def test_irq_restored_after_success(self):
        fake = FakeRemote()
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "irq.json"
            result = run_phase.with_optional_irq1(True, evidence, lambda: "ok", fake)
            self.assertEqual(result, "ok")
            self.assertEqual(fake.mask, "3")
            state = json.loads(evidence.read_text())
            self.assertTrue(state["restored"])
            self.assertTrue(state["restoration_attempted"])

    def test_irq_restored_after_phase_failure(self):
        fake = FakeRemote()
        def fail():
            raise RuntimeError("injected phase failure")
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "irq.json"
            with self.assertRaisesRegex(RuntimeError, "injected"):
                run_phase.with_optional_irq1(True, evidence, fail, fake)
            self.assertEqual(fake.mask, "3")
            state = json.loads(evidence.read_text())
            self.assertTrue(state["restored"])
            self.assertIn("injected phase failure", state["phase_error"])

    def test_irq_restore_attempted_if_pin_write_fails(self):
        fake = FakeRemote()
        original = fake.__call__
        def fail_first_pin(command, timeout=10, input_data=None):
            if command == "echo 2 > /proc/irq/35/smp_affinity":
                fake.calls.append(command)
                raise RuntimeError("injected pin failure")
            return original(command, timeout, input_data)
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "irq.json"
            with self.assertRaisesRegex(RuntimeError, "pin failure"):
                run_phase.with_optional_irq1(True, evidence, lambda: None, fail_first_pin)
            self.assertIn("echo 3 > /proc/irq/35/smp_affinity", fake.calls)
            self.assertTrue(json.loads(evidence.read_text())["restored"])

    def test_irq_restoration_failure_is_fatal(self):
        fake = FakeRemote()
        original = fake.__call__
        def fail_restore(command, timeout=10, input_data=None):
            if command == "echo 3 > /proc/irq/35/smp_affinity":
                raise RuntimeError("injected restore failure")
            return original(command, timeout, input_data)
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "irq.json"
            with self.assertRaisesRegex(RuntimeError, "IRQ restoration failed"):
                run_phase.with_optional_irq1(True, evidence, lambda: None, fail_restore)
            state = json.loads(evidence.read_text())
            self.assertFalse(state["restored"])
            self.assertIn("restore failure", state["restoration_error"])

    def test_recorded_schedule_rejects_more_jobs_than_offsets(self):
        args = argparse.Namespace(name="cadence", candidate="rankunroll", jobs=331,
            period=120, seconds=60, capture_seconds=45, capture_rate=2_500_000,
            recorded_arrivals=True)
        with self.assertRaisesRegex(ValueError, "recorded arrival schedule"):
            run_phase.validate(args)


if __name__ == "__main__":
    unittest.main()
