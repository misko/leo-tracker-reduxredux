"""Run the separately frozen v2 profile on the existing development snippets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from leo.storage import RecordingStore
from tools.research.joint_template_source_isolation import seeded_group_split
from tools.research.replay_joint_pilot_isolation import COUNT, ROOT, tones
from tools.research.shared_cfo_optimizer_v2 import fit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    base = ROOT / "reports/figures/2026_09_23_joint_pilot_isolation"
    paths = sorted(base.glob("probe-*.json"))
    if len(paths) != 6:
        raise ValueError("six inputs required")
    sources = paths + [
        Path(__file__),
        ROOT / "tools/research/shared_cfo_optimizer_v2.py",
        ROOT / "tools/research/joint_template_source_isolation.py",
        ROOT / "tools/research/replay_joint_pilot_isolation.py",
        ROOT / "src/leo/analysis/starlink/templates.py",
        ROOT / "reports/2026_09_23_shared_cfo_v2_protocol.md",
    ]
    binding = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
    }
    (args.output / "binding.json").write_text(json.dumps(binding, indent=2) + "\n")
    store = RecordingStore.open_read_only(Path("/srv/bulk/leo"))
    try:
        bundle = store.inspect("cap-20260825T010019-89c2889553e0")
        reader = store.reader(bundle, "stream-1", verify=True)
        for index, path in enumerate(paths):
            data = json.loads(path.read_text())
            nominal = np.array(
                [[r["tracking_cfo_hz"] for r in data["nominees"][str(rx)]] for rx in (0, 1)]
            )
            initial = np.array(
                [
                    data["receivers"][str(rx)]["models"]["exact_ab"]["residual_cfo_hz"]
                    for rx in (0, 1)
                ]
            )
            closure = float(np.diff(nominal[1] - nominal[0])[0])
            row = dict(time_s=data["time_s"], nominal_closure_hz=closure)
            if abs(closure) > 10000:
                row["abstention"] = "fixed-alias common-offset bounds infeasible"
            else:
                raw = reader.read(data["sample_start"], COUNT, receiver_ids=(0, 1))
                if hashlib.sha256(raw.tobytes()).hexdigest() != data["raw_sha256"]:
                    raise ValueError("changed raw snippet")
                n = np.arange(COUNT)
                mask = (n % 250 >= 16) & (n % 250 < 234)
                split = seeded_group_split(n // 250, seed=20260925 + index)
                for label, selected in (("train", mask & split), ("held", mask & ~split)):
                    digest = hashlib.sha256(n[selected].astype("<i8").tobytes()).hexdigest()
                    assert all(
                        digest == data["receivers"][str(rx)][f"{label}_indices_sha256"]
                        for rx in (0, 1)
                    )
                iq = (raw[:, :, 0].astype(float) + 1j * raw[:, :, 1].astype(float)) / 32768
                templates = np.array(
                    [
                        [
                            tones(int(r["local_epoch_sample"]), r["tracking_cfo_hz"])
                            for r in data["nominees"][str(rx)]
                        ]
                        for rx in (0, 1)
                    ]
                )[:, :, :, mask]
                for name, shared in (("independent", False), ("shared", True)):
                    row[name] = fit(
                        iq[mask], templates, n[mask], split[mask], nominal, initial, shared
                    )
                    print(index, name, row[name]["training_objective_history"], flush=True)
                row["held_energy_by_receiver"] = np.sum(
                    abs(iq[mask & ~split]) ** 2, axis=0
                ).tolist()
            (args.output / f"probe-{index}.json").write_text(
                json.dumps(row, indent=2, allow_nan=False) + "\n"
            )
    finally:
        store.close()


if __name__ == "__main__":
    main()
