from hashlib import sha256
import json
from pathlib import Path

import pytest


@pytest.fixture
def hardware_free_trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/"reports/ALGO08/v3"))
    import clean_saved_0169_trial

    return clean_saved_0169_trial


def test_reverse_order_requires_a_qualified_threshold_near_block(hardware_free_trial):
    review = hardware_free_trial.reverse_needed

    def comparison(speedup, qualified=True):
        return dict(qualified=qualified, times={"elapsed_s": {"admitted_speedup": speedup}})

    assert review(comparison(1.59))
    assert not review(comparison(1.51))
    assert not review(comparison(1.69))
    assert not review(comparison(1.59, qualified=False))


def test_elapsed_counts_the_same_common_setup_once_in_each_hypothetical_request(hardware_free_trial):
    def timing(wall, cpu):
        return dict(elapsed_s=wall, cpu_s=cpu)

    price = hardware_free_trial.ratio(dict(installed=timing(16, 15), routed=timing(10, 9)),
                                     dict(installed=timing(.1, .05), routed=timing(.2, .1)), timing(.3, .2))
    assert price["elapsed_s"]["admitted"] == pytest.approx(dict(installed=16.4, routed=10.5))
    assert price["elapsed_s"]["child_speedup"] == 1.6
    assert price["cpu_s"]["admitted"] == pytest.approx(dict(installed=15.25, routed=9.3))


def test_arbitrary_saved_mapping_authenticates_request_and_inventory(monkeypatch, tmp_path, hardware_free_trial):
    import clean_saved_publication as worker
    import exact_named_route as exact

    def write(name, value):
        file = tmp_path/name
        file.write_text(json.dumps(value))
        return str(file), sha256(file.read_bytes()).hexdigest()

    monkeypatch.setattr(exact, "resident_path", lambda path: path)
    packet = dict(local_archive={"root": str(tmp_path/"tle")}, issued=5, admitted=4)
    req, inv = write("some-request.json", packet), write("some-inventory.json", {"original": True})
    mapping = dict(request=req[0], inventory=inv[0], packets=dict((req, inv)), archive=packet["local_archive"]["root"],
                   issued=5, admitted=4)
    document, pin = write("mapped-job.json", dict(binding=mapping, original_archive={"signature": "causal"}))
    bound, values = worker.load_job(Path(document), pin)
    assert bound == mapping and values["original_archive"] == {"signature": "causal"}
    Path(inv[0]).write_text("changed")
    with pytest.raises(ValueError, match="Unreviewed bootstrap input"):
        worker.load_job(Path(document), pin)
