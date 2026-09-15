"""Independent association of retained ARM visit transitions and native snapshots."""

import json
from pathlib import Path
import sys

from tools.starlink_glrt_tracking_abi import TrackingSnapshot


def review(root, text=None):
    root = Path(root)
    op = json.loads((root / "operator.json").read_text())
    if text is None:
        text = (root / "visits.txt").read_text()
    rows = text.splitlines()
    plan = rows[0].split()
    assert plan == [
        "plan",
        str(op["rate"]),
        op["serial"],
        *map(str, op["lo_plan_hz"]),
        "1536",
        "2",
        "60000000000",
    ]
    assert rows[-1] == "terminal 0"
    snapshot = None
    visits = []
    last_native = 0
    last_gen = 0
    for row in rows[1:-1]:
        kind, raw = row.split(" ", 1)
        if kind == "snapshot":
            snapshot = TrackingSnapshot.from_sysfs(raw)
            snapshot.require_drained()
            assert snapshot.rate == op["rate"] and not snapshot.status & 16
            assert (
                snapshot.faults
                == snapshot.configured
                == snapshot.cdc_drops
                == snapshot.pacer_drops
                == 0
            )
            assert snapshot.latest_index >= last_native
            last_native = snapshot.latest_index
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
            assert result == 0 and idle == fixed == 1
            assert (epoch, rate, latest) == (
                snapshot.epoch,
                snapshot.rate,
                snapshot.latest_index,
            ), "retained snapshot differs from validated visit state"
            visits.append(dict(kind=name, visit=number, epoch=epoch, latest=latest, lo=lo))
            snapshot = None
    assert len(visits) == 6
    for n in range(2):
        before, tuned, after = visits[n * 3 : n * 3 + 3]
        assert before["epoch"] == tuned["epoch"] and tuned["epoch"] + 1 == after["epoch"]
        assert before["latest"] <= tuned["latest"] < after["latest"]
        assert abs(tuned["lo"] - op["lo_plan_hz"][n]) <= 16 and after["lo"] == tuned["lo"]
        child = json.loads((root / f"visit-{n}/independent-visit-review.json").read_text())
        assert child["status"] == "pass" and child["epoch_bindings"][0][1] == after["epoch"]
        assert tuned["latest"] < child["epoch_bindings"][0][2] < after["latest"]
        assert child["exported_samples"] == 25165824
        if n:
            previous = visits[n * 3 - 1]
            assert (before["epoch"], before["lo"]) == (previous["epoch"], previous["lo"])
            assert before["latest"] >= previous["latest"]
    return dict(
        status="pass",
        scope="ARM_local_two_frequency_transition_association",
        visits=visits,
        nominal_lo_hz=op["lo_plan_hz"],
        rf_seconds=20.1326592,
        native_tracking_qualified=False,
    )


if __name__ == "__main__":
    root = Path(sys.argv[1])
    result = review(root)
    with (root / "independent-sequence-review.json").open("x") as out:
        json.dump(result, out, indent=2)
        out.write("\n")
    print(json.dumps(result))
