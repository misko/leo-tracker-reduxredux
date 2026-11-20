"""Try one independent energy envelope on held saved-IQ timing neighborhoods."""

import argparse
import gzip
import json
from contextlib import ExitStack
from pathlib import Path
from time import process_time
from unittest.mock import patch

from ..__main__ import local_output, save_json, write
from ..variants import epoch_carry_power, iq_stream
from . import epoch_carry_trial as base
from . import scout_budget_eval as scout
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import BULK, _load_case, _sha
from .pilot_kernel_eval import _windows
from .portable_gate_trials import compressed_rows
from .scout_budget_build import ROOT as STOCK
from .wide_regional_eval import CHUNK_PREFIX, synthetic, templates

OUT = base.OUT / "envelope"
CASES = ("DS26-0014", "DS29-0127")
SCHEDULE = ((9, (3, 8, 13, 18)), (13, (3, 8, 13, 18)))
RATE = 10_000_000


def staged(work):
    release = scout.release(STOCK)
    build = STOCK / "scout16/build-receipt.json"
    prior = json.loads(build.read_bytes())
    static = STOCK / "scout16/libleo-adaptive-detector.a"
    if _sha(static) != prior["outputs"][static.name]:
        raise ValueError("the native scout probe static archive changed")
    work.mkdir(exist_ok=False, parents=True)
    (work / "scout16").symlink_to(STOCK / "scout16", target_is_directory=True)
    (work / "scout16-source").symlink_to(STOCK / "scout16-source", target_is_directory=True)
    (work / "compiler-temp").mkdir()
    return scout.make_probe(work), release


def replay(work, probe, release):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    data = []
    for ident in CASES:
        item = _load_case(ident)
        for seg, sequences in SCHEDULE:
            with patch.object(iq_stream, "MAX_CHUNK_PREFIX", CHUNK_PREFIX):
                windows = _windows(item, seg, sequences)
            for window in windows:
                data.append(
                    (
                        window,
                        dict(
                            id=ident,
                            visit=window.acquisition["global_visit"],
                            condition="recorded",
                            segment_sha256=item["recording"]["segments"][seg]["sha256"],
                        ),
                    )
                )
    for side, frequency in (("lower", -611_121), ("upper", 671_435)):
        for mode in ("planted", "noise"):
            plant = [(735, frequency, 1800)] if mode == "planted" else []
            data.append(
                (
                    _test_signal(
                        synthetic(RATE, side),
                        plant,
                        64977 + (mode == "noise") + (side == "upper") * 31,
                    ),
                    dict(id=side, condition=mode),
                )
            )
    specs = []
    with ExitStack() as stack:
        for side in ("lower", "upper"):
            exact, ctrl = templates(RATE, side)
            folder = work / side
            folder.mkdir()
            (folder / "pilot.c128").write_bytes(exact.tobytes())
            model = epoch_carry_power.PilotEnvelope(exact)
            ctx = stack.enter_context(
                NativeShortWindow(
                    release["paths"]["control"],
                    exact,
                    ctrl,
                    sample_rate_hz=RATE,
                    receiver_count=2,
                    fractional_epoch=True,
                )
            )
            specs.append((side, dict(folder=folder, model=model, context=ctx)))
        save_json(
            OUT / "plan.json",
            dict(
                inputs=[dict(label, iq_sha256=w.iq_sha256) for w, label in data],
                control=release["library_sha256"]["control"],
                scout_probe_sha256=_sha(probe),
                files={
                    p.name: _sha(p)
                    for p in (Path(__file__), Path(epoch_carry_power.__file__), OUT / "PROTOCOL.md")
                },
            ),
        )
        by_side = dict(specs)
        for w, label in data:
            env = by_side[w.target["edge"]]
            old = [
                r[:4]
                for r in scout.centers_for(
                    probe, w.samples, env["folder"], env["folder"] / "pilot.c128"
                )
            ]
            t = process_time()
            results = [env["model"].select(w.samples[:, rx, :], old[rx]) for rx in range(2)]
            spent = process_time() - t
            exact = env["context"].analyze(w.samples, include_timings=True)
            yield dict(
                label,
                iq_sha256=w.iq_sha256,
                edge=w.target["edge"],
                stock=old,
                alternate=[r[0] for r in results],
                proposals=[r[1] for r in results],
                detector=exact,
                prototype_cpu_ms=1000 * spent,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("predict", "score"))
    parser.add_argument("--work", type=local_output)
    args = parser.parse_args()
    if args.action == "predict":
        probe, release = staged(args.work)
        raw = OUT / "predictions.jsonl.gz"
        write(raw, compressed_rows(replay(args.work, probe, release)))
        save_json(
            OUT / "prediction-lock.json",
            dict(files={p.name: _sha(p) for p in (raw, OUT / "plan.json")}),
        )
        return
    pin = json.loads((OUT / "prediction-lock.json").read_bytes())
    for name, digest in pin["files"].items():
        assert _sha(OUT / name) == digest
    archives = {}
    for ident in CASES:
        item = _load_case(ident)
        path = BULK / item["native"]["path"]
        assert _sha(path) == item["native"]["sha256"]
        source = json.loads(path.read_bytes())["source"]
        archives[ident] = {
            (p["visit_index"], p["receiver_id"]): p["candidates"] for p in source["probes"]
        }
    results = []
    for line in gzip.decompress((OUT / "predictions.jsonl.gz").read_bytes()).splitlines():
        r = json.loads(line)
        teacher = []
        for rx in range(2):
            if r["condition"] == "recorded":
                candidates = archives[r["id"]].get((r["visit"], rx), [])
                teacher.append(
                    [
                        c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]
                        for c in candidates
                        if c["passed_fractional_margin_gate"]
                    ]
                )
            elif r["condition"] == "planted":
                teacher.append([735])
            else:
                teacher.append([])
        coverage = {}
        for kind in ("stock", "alternate"):
            coverage[kind] = {}
            for radius in (1, 2):
                coverage[kind][radius] = sum(
                    any(epoch_carry_power.distance(t, c) <= radius for c in r[kind][rx])
                    for rx in range(2)
                    for t in teacher[rx]
                )
        results.append(
            dict(
                id=r["id"],
                visit=r.get("visit"),
                condition=r["condition"],
                coverage=coverage,
                teacher_candidates=sum(map(len, teacher)),
                replaced=sum(a != b for a, b in zip(r["stock"], r["alternate"], strict=True)),
                prototype_cpu_ms=r["prototype_cpu_ms"],
                ordinary_scout_cpu_ms=sum(
                    x["timings_ms"]["proposal"] for x in r["detector"]["rows"]
                ),
            )
        )
    save_json(OUT / "scores.json", dict(rows=results))


if __name__ == "__main__":
    main()
