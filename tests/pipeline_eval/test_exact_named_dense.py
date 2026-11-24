from copy import deepcopy

import pytest

from reports.ALGO08.v3.exact_named_dense import reduce_panel, request_view


def test_dense_request_view_keeps_collection_and_signed_snapshot_order():
    archive = dict(snapshots_sha256="sha256:catalogue", logical_bytes=150, snapshots=3, root="/dev/shm/archive")
    original = dict(archive=archive, local_archive=archive, manifests=[["a", "sig-a"], ["b", "sig-b"]],
                    causal_cutoff_utc_ns=20, issued=6770, admitted=4644)
    snapshot = deepcopy(original)
    authority = dict(snapshots_sha256="sha256:catalogue", root="/original")
    view = request_view(original, authority)
    assert original == snapshot
    assert view["original_archive"] == authority and view["local_archive"]["bytes"] == 150
    assert view["local_archive"]["root"] == "/dev/shm/archive"
    assert view["manifests"] == original["manifests"] and view["causal_cutoff_utc_ns"] == 20
    with pytest.raises(ValueError, match="signed causal catalogue differ"):
        request_view(original, {**authority, "snapshots_sha256": "sha256:changed"})


def test_panel_distinguishes_weighted_total_from_typical_case_and_gate():
    items = []
    for before, after in ((4, 2), (8, 5), (40, 40)):
        items.append(dict(clocks=dict(named=dict(elapsed_s=before, cpu_s=before),
                                      candidate=dict(elapsed_s=after, cpu_s=after)),
                          speedup=dict(elapsed_s=before/after, cpu_s=before/after)))
    panel = reduce_panel(items)
    assert panel["elapsed_s"] == panel["cpu_s"]
    wall = panel["elapsed_s"]
    assert wall["total_ratio"] == pytest.approx(52/47) and wall["median_ratio"] == 1.6
    assert not wall["total_target_met"] and wall["median_target_met"]
    assert wall["case_target_count"] == 2
