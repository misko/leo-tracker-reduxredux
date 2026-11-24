from reports.ALGO08.v3.next_complete_original import MAX_BYTES, choose, enrollment


def entry(label, size, count=820):
    chunk = dict(compressed_bytes=size, observed_payload_bytes=size, index_bytes=140, window_count=count)
    return dict(dataset_label=label, recording_state="incomplete", sample_rate_hz=10_000_000, window_count=count,
                raw_recording=dict(root="/srv/bulk/source", segments=[1], integrity_errors=[], chunks=[chunk]))


def test_eligible_later_binding_can_cover_an_interrupted_capture():
    ids = ["DS30-0050", "DS30-0051", "DS30-0052", "DS30-0053"]
    data = [entry(ids[0], 1_203), entry(ids[1], 1_211), entry(ids[2], MAX_BYTES), entry(ids[3], 140, count=100)]
    pins = {key: dict(binding_sha256="opaque", usable_visits=500) for key in ids}
    assert choose({"members": data}, pins, {ids[1], ids[2]})["selected"]["case"] == ids[1]
    assert choose({"members": data}, pins, {ids[2]})["selected"]["case"] == ids[0]


def test_bound_original_uses_the_frozen_opaque_size_order():
    all_cases = enrollment()
    selected = all_cases["selected"]
    assert (selected["case"], selected["encoded_bytes"], selected["visits"]) == ("DS30-0049", 1_202_056_196, 986)
    assert not selected["release"] and selected["admitted"] == 932
    assert all_cases["smallest_release"][0]["encoded_bytes"] > MAX_BYTES
