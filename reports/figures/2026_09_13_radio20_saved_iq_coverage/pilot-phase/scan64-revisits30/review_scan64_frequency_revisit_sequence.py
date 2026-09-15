"""Independent association of retained ARM visit transitions and native snapshots."""

import json
from pathlib import Path
import sys

from tools.starlink_glrt_tracking_abi import TrackingSnapshot


def review(root, text=None, children=None):
    root = Path(root)
    op = json.loads((root / "operator.json").read_text())
    if text is None:
        text = (root / "visits.txt").read_text()
    count = op["visit_count"]
    assert count in (3, 4)
    assert len(op["lo_plan_hz"]) == count
    assert all(a != b for a, b in zip(op["lo_plan_hz"], op["lo_plan_hz"][1:]))
    if children is None:
        children = [
            json.loads((root / f"visit-{n}/independent-visit-review.json").read_text())
            for n in range(count)
        ]
    assert len(children) == count
    rows = text.splitlines()
    plan = rows[0].split()
    assert plan == [
        "plan",
        str(op["rate"]),
        op["serial"],
        *map(str, op["lo_plan_hz"]),
        "1536-selected-observer3-scan64",
        str(count),
        "60000000000",
    ]
    assert rows[-1] == "terminal 0"
    snapshot = None
    visits = []
    last_native = 0
    last_gen = 0
    boot_counters = []
    for row in rows[1:-1]:
        kind, raw = row.split(" ", 1)
        if kind == "snapshot":
            snapshot = TrackingSnapshot.from_sysfs(raw)
            snapshot.require_drained()
            assert snapshot.rate == op["rate"] and not snapshot.status & 16
            assert snapshot.faults == snapshot.configured == 0
            if snapshot.epoch:
                assert snapshot.cdc_drops == snapshot.pacer_drops == 0
            else:
                assert len(visits) < 2  # boot counters only before the first acquired epoch
                boot_counters.append([snapshot.cdc_drops, snapshot.pacer_drops])
            assert snapshot.latest_index >= last_native
            assert snapshot.generation > last_gen
            last_native = snapshot.latest_index
            last_gen = snapshot.generation
        else:
            assert kind == "visit" and snapshot is not None
            name, number, result, lo, rate, epoch, latest, idle, fixed = raw.split()
            number, result, lo, rate, epoch, latest, idle, fixed = map(
                int, (number, result, lo, rate, epoch, latest, idle, fixed)
            )
            assert (
                name == ["before_tune", "tuned", "after_run"][len(visits) % 3]
                and number == len(visits) // 3
            )
            assert result in ((0, 1) if name == "after_run" else (0,)) and idle == fixed == 1
            assert (epoch, rate, latest) == (
                snapshot.epoch,
                snapshot.rate,
                snapshot.latest_index,
            ), "retained snapshot differs from validated visit state"
            visits.append(
                dict(kind=name, visit=number, result=result, epoch=epoch, latest=latest, lo=lo)
            )
            snapshot = None
    assert len(visits) == 3 * count
    for n in range(count):
        before, tuned, after = visits[n * 3 : n * 3 + 3]
        assert before["epoch"] == tuned["epoch"] and tuned["epoch"] + 1 == after["epoch"]
        assert before["latest"] <= tuned["latest"] < after["latest"]
        assert abs(tuned["lo"] - op["lo_plan_hz"][n]) <= 16 and after["lo"] == tuned["lo"]
        child = children[n]
        assert child["status"] == "pass" and child["epoch_bindings"][0][1] == after["epoch"]
        assert tuned["latest"] < child["epoch_bindings"][0][2] < after["latest"]
        assert 0 < child["returned_samples"] <= child["exported_samples"] <= 25165824
        assert child["probe_sha256"] == op["payload_sha256"]["probe"]
        assert child["child_disposition"] == (3 if after["result"] == 1 else 0)
        if after["result"] == 1:
            assert child["clean_loss"]["status"] == "pass"
            assert child["clean_loss"]["epoch"] == after["epoch"]
        if n:
            previous = visits[n * 3 - 1]
            assert (before["epoch"], before["lo"]) == (previous["epoch"], previous["lo"])
            assert before["latest"] >= previous["latest"]
    return dict(
        status="pass",
        scope="ARM_local_bounded_frequency_revisit_association",
        visits=visits,
        pre_acquisition_epoch_zero_counters=boot_counters,
        nominal_lo_hz=op["lo_plan_hz"],
        rf_seconds=sum(c["rf_seconds"] for c in children),
        native_tracking_qualified=False,
    )


if __name__ == "__main__":
    root = Path(sys.argv[1])
    result = review(root)
    with (root / "independent-sequence-review.json").open("x") as out:
        json.dump(result, out, indent=2)
        out.write("\n")
    print(json.dumps(result))
