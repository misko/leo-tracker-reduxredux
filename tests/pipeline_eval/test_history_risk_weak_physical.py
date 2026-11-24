from copy import deepcopy

import pytest

from reports.ALGO08.v3.history_risk_weak_physical import deny_original, validate_selection


def test_complete_weak_selection_rejects_any_changed_probe():
    probes = [{"probe_index": i} for i in range(1426)]
    original = dict(source=dict(probes=probes, raw_recording_authority_digest="signed"),
                    clock_anchor=dict(before=dict(realtime_ns=1)))
    native = deepcopy(original)
    req = dict(native="sha256:native", detector="sha256:detector", authority="signed", cutoff_utc_ns=1)
    choice = dict(route="unfiltered", log_score_gain_by_radio={"0": -25.29, "1": -11.75})
    selection = dict(native_sha256="sha256:native", selected=506, refinement_calls=0,
                     choice=dict(route="unfiltered", log_score_gain_by_radio={0: -25.29, 1: -11.75}))
    validate_selection(native, original, "detector", selection, req, choice)
    native["source"]["probes"][24]["probe_index"] = 0
    with pytest.raises(ValueError, match="complete physical"):
        validate_selection(native, original, "detector", selection, req, choice)


@pytest.mark.parametrize("path", ["/srv/bulk", "/srv/./bulk/recording", "/mnt/qnap01/recording"])
def test_saved_physical_audit_rejects_original_backing(path):
    with pytest.raises(ValueError, match="original backing"):
        deny_original("open", (path,))
    deny_original("open", ("/dev/shm/native.json",))
