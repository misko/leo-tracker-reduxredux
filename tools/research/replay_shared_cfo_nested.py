"""Complete the known-solution nesting check without selecting on held errors."""

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


def select_training_candidate(candidates):
    """Stable training-only minimum; shared solutions are valid independent fits."""
    if not candidates or any(not np.isfinite(v["train_sse"]) for v in candidates.values()):
        raise ValueError("finite training candidates required")
    name = min(candidates, key=lambda key: candidates[key]["train_sse"])
    return name, candidates[name]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    original = ROOT / "reports/figures/2026_09_23_joint_pilot_isolation"
    previous = ROOT / "reports/figures/2026_09_23_shared_receiver_cfo_v2"
    for name, digest in json.loads((previous / "binding.json").read_text()).items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("frozen v2 source changed")
    paths = sorted(previous.glob("probe-*.json"))
    if len(paths) != 6:
        raise ValueError("six bound opportunities required")
    sources = (
        paths
        + list(original.glob("probe-*.json"))
        + [
            Path(__file__),
            ROOT / "tools/research/shared_cfo_optimizer_v2.py",
            ROOT / "tools/research/replay_joint_pilot_isolation.py",
            ROOT / "tools/research/joint_template_source_isolation.py",
            ROOT / "src/leo/analysis/starlink/templates.py",
            ROOT / "reports/2026_09_23_shared_cfo_nested_protocol.md",
        ]
    )
    binding = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
    }
    (args.output / "binding.json").write_text(json.dumps(binding, indent=2) + "\n")
    store = RecordingStore.open_read_only(Path("/srv/bulk/leo"))
    try:
        bundle = store.inspect("cap-20260825T010019-89c2889553e0")
        reader = store.reader(bundle, "stream-1", verify=True)
        for index, path in enumerate(paths):
            old = json.loads(path.read_text())
            row = dict(time_s=old["time_s"])
            if "abstention" in old:
                row["abstention"] = old["abstention"]
            else:
                data = json.loads((original / path.name).read_text())
                nominal = np.array(
                    [[r["tracking_cfo_hz"] for r in data["nominees"][str(rx)]] for rx in (0, 1)]
                )
                raw = reader.read(data["sample_start"], COUNT, receiver_ids=(0, 1))
                if hashlib.sha256(raw.tobytes()).hexdigest() != data["raw_sha256"]:
                    raise ValueError("changed snippet")
                n = np.arange(COUNT)
                mask = (n % 250 >= 16) & (n % 250 < 234)
                split = seeded_group_split(n // 250, seed=20260925 + index)
                for label, support in (("train", mask & split), ("held", mask & ~split)):
                    digest = hashlib.sha256(n[support].astype("<i8").tobytes()).hexdigest()
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
                new = fit(
                    iq[mask],
                    templates,
                    n[mask],
                    split[mask],
                    nominal,
                    np.array(old["shared"]["residual_cfo_hz"]),
                    False,
                )
                if abs(new["training_objective_history"][0] - old["shared"]["train_sse"]) > 1e-9:
                    raise ValueError("embedded shared training score did not reproduce")
                candidates = {
                    "previous_independent": old["independent"],
                    "embedded_shared": old["shared"],
                    "shared_seed_refinement": new,
                }
                name, selected = select_training_candidate(candidates)
                if selected["train_sse"] > old["shared"]["train_sse"] + 1e-10:
                    raise ValueError("nesting failed")
                row.update(
                    candidates=candidates,
                    selected_independent=name,
                    shared=old["shared"],
                    independent=selected,
                    held_energy_by_receiver=old["held_energy_by_receiver"],
                )
                residual = np.array(selected["residual_cfo_hz"])
                row["independent_closure_hz"] = float(
                    np.diff(nominal[1] - nominal[0] + residual[1] - residual[0])[0]
                )
                row["held_loss_percentage_points"] = [
                    (s["held_sse"] - i["held_sse"]) / e * 100
                    for s, i, e in zip(
                        old["shared"]["receivers"],
                        selected["receivers"],
                        old["held_energy_by_receiver"],
                        strict=True,
                    )
                ]
                print(
                    row["time_s"],
                    name,
                    row["independent_closure_hz"],
                    row["held_loss_percentage_points"],
                    flush=True,
                )
            (args.output / path.name).write_text(json.dumps(row, indent=2, allow_nan=False) + "\n")
    finally:
        store.close()


if __name__ == "__main__":
    main()
