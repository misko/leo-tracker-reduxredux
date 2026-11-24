import json

import pytest

from field_crossover_admission_watch import MOVED_TO, OVERFLOW, RECORD, RECENCY_NS, recent_deferral, replaced_export


def signal(mask, name):
    raw = name.encode()+b"\0"
    raw += b"\0"*((-len(raw))%4)
    return RECORD.pack(1, mask, 0, len(raw))+raw


def test_only_an_atomic_rows_replacement_wakes_the_gate():
    assert not replaced_export(signal(MOVED_TO, "row.bin")+signal(2, "rows.jsonl"))
    assert replaced_export(signal(MOVED_TO, "row.bin")+signal(MOVED_TO, "rows.jsonl"))
    with pytest.raises(ValueError, match="overflow"):
        replaced_export(signal(OVERFLOW, ""))


def test_gate_needs_the_latest_official_deferral_after_start(tmp_path):
    case = "DS30-0123"
    folder = tmp_path/"cases"/case/"events"
    folder.mkdir(parents=True)
    export = tmp_path/"rows.jsonl"
    row = dict(case=case, admission_state="deferred_storage_busy", verified_pair=False)
    export.write_text(json.dumps(row)+"\n")

    start = 1_000_000_000_000
    now = start+RECENCY_NS+10

    def event(stamp, state):
        (folder/f"{stamp:020d}-event.json").write_text(json.dumps(dict(state=state)))

    event(start-1, "deferred_storage_busy")
    assert recent_deferral(tmp_path, start, now) is None
    event(start+1, "deferred_storage_busy")
    assert recent_deferral(tmp_path, start, now) is None
    event(now-2, "deferred_storage_busy")
    assert recent_deferral(tmp_path, start, now)["unix_ns"] == now-2
    event(now-1, "metadata_admitted")
    assert recent_deferral(tmp_path, start, now) is None
    event(now, "deferred_storage_busy")
    row["verified_pair"] = True
    export.write_text(json.dumps(row)+"\n")
    assert recent_deferral(tmp_path, start, now) is None
