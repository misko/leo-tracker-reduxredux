import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [
    str(HERE.parent / "2026_09_29_waveform_uncertainty"),
    str(HERE.parent / "2026_09_29_waveform_trajectory"),
]
from model import line_predict  # noqa: E402
from study import errors, frames_for  # noqa: E402


def convert(measured, actual_rf, cached):
    native = measured * actual_rf / 11.2e9
    alias = (native - cached) * 4.4e-6
    assert abs(alias - round(alias)) < 1e-8
    return float(native), int(round(alias))


def main():
    hashes = {}
    outputs = {}
    for name, directory in (
        ("two_point", "2026_09_29_waveform_trajectory"),
        ("four_point", "2026_09_29_waveform_uncertainty"),
    ):
        folder = HERE.parent / directory
        docs = {
            n: json.loads((folder / f"{n}.json").read_text())
            for n in ("plan", "inventory", "results")
        }
        for n, doc in docs.items():
            path = folder / f"{n}.json"
            hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
            for p, digest in doc["hashes"].items():
                assert hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == digest
        selected = {(r["unit_id"], r["receiver_id"]): r for r in docs["plan"]["selections"]}
        groups, audit = {}, []
        for row in docs["inventory"]["rows"]:
            assert row["status"] == "ok"
            s = selected[row["unit_id"], row["receiver_id"]]
            track = s["track"]
            i = s["observation_index"]
            assert row["track_id"] == track["track_id"]
            assert row["visit"] == track["visits"][i]
            assert row["time_s"] == track["times_s"][i]
            assert row["actual_rf_hz"] == track["rf_hz"]
            native, alias = convert(
                track["measured_hz"][i],
                row["actual_rf_hz"],
                row["candidate"]["fractional_tracking_cfo_hz"],
            )
            entry = dict(row, native_dealiased_hz=native, additive_alias=alias)
            groups.setdefault((row["panel_id"], row["receiver_id"]), {})[row["role"]] = entry
            audit.append(
                dict(
                    panel_id=row["panel_id"],
                    receiver_id=row["receiver_id"],
                    role=row["role"],
                    visit=row["visit"],
                    additive_alias=alias,
                    native_dealiased_hz=native,
                )
            )
        rows = []
        max_replay = 0.0
        for prior in docs["results"]["rows"]:
            assert prior["status"] == "ok"
            group = groups[prior["panel_id"], prior["receiver_id"]]
            assert len({r["actual_rf_hz"] for r in group.values()}) == 1
            if name == "two_point":
                training = [group[r] for r in ("A", "B")]
                held = [group["H"]]
                correction = np.array(prior["residual_corrections_hz"][:2])
                sigmas = None
                previous_held = [dict(arms=prior["arms"])]
                names = ("cached_trajectory", "long_trajectory")
            else:
                training = [group[f"T{i}"] for i in range(4)]
                held = [group[k] for k in sorted(group) if k.startswith("H")]
                correction = np.array([r["residual_frequency_hz"] for r in prior["training"]])
                sigmas = [r["sigma_hz"] for r in prior["training"]]
                previous_held = prior["held"]
                names = ("cached_ols", "refined_ols", "cached_wls", "refined_wls")
            times = [r["time_s"] for r in training]
            targets = [r["time_s"] for r in held]
            cached = np.array([r["native_dealiased_hz"] for r in training])
            predictions = {}
            for j, arm in enumerate(names):
                values = cached + correction if j % 2 else cached
                predictions[arm], _ = line_predict(
                    times, values, targets, sigmas if j >= 2 else None
                )
            evaluations = []
            for i, (h, old) in enumerate(zip(held, previous_held, strict=True)):
                frames = frames_for(h)
                for arm, saved in old["arms"].items():
                    replay = errors(frames, saved["residual_frequency_hz"])
                    difference = float(np.max(abs(replay - saved["frame_nmse"])))
                    assert difference < 1e-10
                    max_replay = max(max_replay, difference)
                residuals = {
                    arm: float(p[i] - h["native_dealiased_hz"]) for arm, p in predictions.items()
                }
                residuals["cached_held"] = 0.0
                evaluations.append(
                    dict(
                        visit=h["visit"],
                        arms={
                            arm: dict(
                                residual_frequency_hz=f, frame_nmse=errors(frames, f).tolist()
                            )
                            for arm, f in residuals.items()
                        },
                    )
                )
            rows.append(
                dict(
                    panel_id=prior["panel_id"],
                    receiver_id=prior["receiver_id"],
                    aliases=[r["additive_alias"] for r in training + held],
                    held=evaluations,
                )
            )
        summary = {}
        for ds in ("DS7", "DS8", "DS9", "all"):
            chosen = [r for r in rows if ds == "all" or r["panel_id"].startswith(ds)]
            values = {
                arm: np.array(
                    [
                        np.mean([np.mean(h["arms"][arm]["frame_nmse"]) for h in r["held"]])
                        for r in chosen
                    ]
                )
                for arm in (*names, "cached_held")
            }
            gain = values[names[0]] - values[names[1]]
            summary[ds] = dict(
                tracks=len(chosen),
                alias_varying=sum(len(set(r["aliases"])) > 1 for r in chosen),
                mean_nmse={arm: float(np.mean(v)) for arm, v in values.items()},
                improved=int(sum(gain > 1e-10)),
                tied=int(sum(abs(gain) <= 1e-10)),
                mean_gain=float(np.mean(gain)),
                median_gain=float(np.median(gain)),
            )
        outputs[name] = dict(
            audit=audit, rows=rows, summary=summary, maximum_prior_replay_difference=max_replay
        )
    for path in (HERE / "run.py", HERE / "PROTOCOL.md"):
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (HERE / "results.json").write_text(
        json.dumps(dict(hashes=hashes, experiments=outputs), indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps({name: d["summary"] for name, d in outputs.items()}, indent=2))


if __name__ == "__main__":
    main()
