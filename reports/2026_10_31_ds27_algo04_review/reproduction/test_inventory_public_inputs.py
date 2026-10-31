"""Public availability ranking never changes DS27 acquisition membership."""

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "inventory_public_inputs", Path(__file__).with_name("inventory_public_inputs.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_recording_and_public_sessions_are_all_recognized_without_position_fields():
    assert MODULE.identities(
        dict(recording_id="capture", session_id="public", session_ids=["public", "other"])
    ) == {"capture", "public", "other"}


def test_verified_completed_production_preferred_without_discarding_other_public_inputs():
    pending = dict(job_id="aaa", qualified_completed_ALGO02=False)
    complete = dict(job_id="zzz", qualified_completed_ALGO02=True)
    assert MODULE.choose_export([pending, complete]) is complete
    assert MODULE.choose_export([pending]) is pending
    assert MODULE.choose_export([]) is None
