"""Score the sealed fresh paced trials and emit one mixed-roof chart."""

import argparse
from collections import Counter
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution
from . import arrival_queue, fresh_replay
from .fresh_adaptive import CPUS, ORDER, PARENT, REPORT, read
from .fresh_adaptive_position import METHODS, MODES, terminal
from .full_held_scores import held_references
from .full_v5_check import _sha
from .margin_admission_results import fit, sealed
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file


def raw_budget():
    summary = []
    for ident, order in ORDER.items():
        for mode in order:
            name = f"{ident}-{mode}"
            lock = read(REPORT / (name + "-lock.json"))
            for member, digest in lock["files"].items():
                whole_iq.checked(REPORT / member, digest)
            trace = arrival_queue.readgz(REPORT / (name + "-trace.json.gz"))
            counts = Counter(r["outcome"] for r in trace)
            released = [r for r in trace if r["outcome"] == "emitted"]
            dispatch = Counter(r["policy"] for r in released)
            latency = distribution([(r["emitted_ns"] - r["arrival_ns"]) * 1e-6 for r in released])
            lag = distribution([(r["released_ns"] - r["arrival_ns"]) * 1e-6 for r in trace])
            call = distribution([r["native_wall_ns"] * 1e-6 for r in released])
            data = read(REPORT / (name + "-service.json"))
            worker = data["worker"] or {}
            start, end = (worker.get(k, {}) for k in ("start", "end"))
            summary.append(
                dict(
                    id=ident,
                    policy=mode,
                    status=lock["status"],
                    expected=len(arrival_queue.readgz(REPORT / f"{ident}-events.json.gz")),
                    released_visits=len(trace),
                    invalid=counts["invalid_capture"],
                    dropped=counts["queue_drop"],
                    emitted=counts["emitted"],
                    stock4=dispatch["stock"],
                    fifth5=dispatch["fifth"],
                    raw_cgroup_cpu_s=(end["cpu.stat.usage_usec"] - start["cpu.stat.usage_usec"])
                    / 1e6
                    if worker
                    else None,
                    raw_worker_wall_s=end["monotonic_s"] - start["monotonic_s"] if worker else None,
                    fifo_drain_s=max((r["emitted_ns"] for r in released), default=0) / 1e9,
                    native_cpu_s=sum(r["native_cpu_ns"] for r in released) / 1e9,
                    peak_bytes=end.get("memory.peak"),
                    swap_bytes=end.get("memory.swap.current"),
                    native_within_20ms=sum(r["native_wall_ns"] <= 20_000_000 for r in released),
                    emission_age_within_20ms=sum(
                        r["emitted_ns"] - r["arrival_ns"] <= 20_000_000 for r in released
                    ),
                    native_wall_p50_ms=call["p50"],
                    native_wall_p95_ms=call["p95"],
                    emission_age_p50_ms=latency["p50"],
                    emission_age_p95_ms=latency["p95"],
                    release_lag_p95_ms=lag["p95"],
                )
            )
    return summary


def references(deadline):
    fresh_ref = terminal(PARENT / "all-figure-lock.json", deadline)
    docs = ("roof-authority.json", "fresh-v5.jsonl.gz")
    for name in docs:
        raw = whole_iq.checked(PARENT / name, fresh_ref["files"][name]).read_bytes()
        write(REPORT / name, raw)
    (root,) = read(REPORT / docs[0])["cases"]
    if root["id"] != "DS29-0047":
        raise ValueError("new roof reference has different capture authority")
    stock = sealed(PARENT, "reference-prediction-lock.json", docs[1])
    if any(
        r["id"] != root["id"] or any(r[k] != v for k, v in root["bindings"].items()) for r in stock
    ) or {r["method"] for r in stock} != set(ROLES):
        raise ValueError("new original-v5 options differ from the frozen roof authority")
    mapped = {
        row["method"]: {
            arm: dict(
                row["result"]["arms"][arm],
                status=row["result"]["status"],
                error_km=distance_km(root["truth"], row["result"]["arms"][arm]["latlon"]),
            )
            for arm in ARMS
        }
        for row in stock
    }
    (ds26,) = held_references(None, ["DS26-0026"])[1]
    return {ds26["id"]: ds26, root["id"]: dict(root, reference=mapped)}


def positions(rows, refs):
    result = []
    for row in rows:
        for arm in ARMS:
            ref = refs[row["id"]]
            original = ref["reference"]["baseline"][arm]["error_km"]
            entry = fit(row, ref, arm)
            observed = entry["error_km"]
            result.append(
                dict(
                    entry,
                    condition=row["condition"],
                    original_v5_km=original,
                    within_5pct=observed is not None
                    and original is not None
                    and observed <= 1.05 * original,
                    within_10pct=observed is not None
                    and original is not None
                    and observed <= 1.10 * original,
                )
            )
    return result


def archive_parity(rows):
    parent = sealed(PARENT, "prediction-lock.json", "positions.jsonl.gz")
    lookup = {r["id"]: r for r in parent if r["method"] == fresh_replay.CONTROL}
    evidence = []
    for stock in (r for r in rows if r["condition"] == "stock"):
        older = lookup[stock["id"]]
        if older["native_sha256"] != stock["native_sha256"]:
            raise ValueError("the fresh unpaced stock solve differs from the exact detector input")
        for arm in ARMS:
            left, right = (r["result"].get("arms", {}).get(arm, {}) for r in (stock, older))
            live = left.get("latlon") is not None and right.get("latlon") is not None
            evidence.append(
                dict(
                    id=stock["id"],
                    arm=arm,
                    current=stock["result"]["status"],
                    archived=older["result"]["status"],
                    same_coordinate=left["latlon"] == right["latlon"] if live else None,
                    same_rf=left.get("rf_rms_hz") == right.get("rf_rms_hz") if live else None,
                )
            )
    return evidence


def source_amendment():
    import ast
    import gzip

    sources = read(REPORT / "position-plan.json")["sources"]
    runner = next(Path(name) for name in sources if name.endswith("/fresh_adaptive_position.py"))
    old = gzip.decompress((REPORT / "initial-lock/position-runner.py.gz").read_bytes())
    from hashlib import sha256

    if sha256(old).hexdigest() != sources[str(runner)]:
        raise ValueError("archive does not match actual numerical launcher")

    def normalized(source):
        module = ast.parse(source)
        imports = []
        rest = []
        for node in module.body:
            if isinstance(node, ast.ImportFrom):
                imports.extend((node.level, node.module, x.name, x.asname) for x in node.names)
            else:
                rest.append(ast.dump(node))
        return sorted(imports, key=repr), rest

    if normalized(old) != normalized(runner.read_bytes()):
        raise ValueError("the current numerical runner differs beyond import grouping")
    save_json(
        REPORT / "position-runner-audit.json",
        dict(
            actual=sources[str(runner)],
            current=_sha(runner),
            scope="Adjacent imports grouped only, parsed executable statements unchanged",
        ),
    )


def figure():
    names = (
        "positions.jsonl.gz",
        "prediction-lock.json",
        "roof-authority.json",
        "fresh-v5.jsonl.gz",
        "scores.csv",
        "raw-budget.csv",
        "position-resources.csv",
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=list(CPUS), files={n: _sha(REPORT / n) for n in names}),
    )

    def series(key, label, mode):
        return dict(
            key=key,
            label=label,
            file=names[0],
            value=METHODS[mode],
            native_field="paired_capture_sha256",
            match=["catalog_sha256", "original_request_sha256", "tile"],
        )

    save_json(
        REPORT / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="fresh-paced-adaptive",
                    method=METHODS["adaptive"],
                    scope="roof",
                    cases="sealed",
                    title="Adaptive fifth-region admission on two new recordings",
                    caption=(
                        "Actual paced adaptive and always-fifth packets use the same saved "
                        "waveforms. Unpaced stock uses all valid visits."
                    ),
                    seal="figure-lock.json",
                    roof_references=dict(authority=names[2], predictions=names[3]),
                    provenance=list(names[1:]),
                    series=[
                        series("one", "Paced adaptive five or four", "adaptive"),
                        series("stock", "Complete unpaced four-region stock", "stock"),
                        series("one_native_factors", "Paced always fifth", "fifth"),
                    ],
                )
            ],
        ),
    )


def stage(rows):
    import matplotlib.pyplot as plt

    labels = [r["id"] + " " + r["policy"] for r in rows]
    x = list(range(len(rows)))
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
    bottoms = [0] * len(rows)
    for name, label in (
        ("stock4", "Stock four"),
        ("fifth5", "Fifth"),
        ("dropped", "Queue drop"),
        ("invalid", "Invalid capture"),
    ):
        y = [r[name] for r in rows]
        a.bar(x, y, bottom=bottoms, label=label)
        bottoms = [c + d for c, d in zip(bottoms, y, strict=True)]
    a.set(title="Measured raw arrival outcomes", ylabel="Complete physical visits")
    b.bar([i - 0.16 for i in x], [r["emission_age_p50_ms"] for r in rows], width=0.32, label="P50")
    b.bar([i + 0.16 for i in x], [r["emission_age_p95_ms"] for r in rows], width=0.32, label="P95")
    b.axhline(20, color="#665555", linestyle="--", label="20 ms")
    b.set(title="Measured emission age", ylabel="Milliseconds since recorded arrival")
    for axes in (a, b):
        axes.set_xticks(x, labels, rotation=20)
        axes.legend(fontsize=8)
    fig.savefig(REPORT / "fresh-arrival.png", dpi=160)
    plt.close(fig)
    assets = ("fresh-arrival.png", "raw-budget.csv")
    save_json(REPORT / "stage-lock.json", dict(files={n: _sha(REPORT / n) for n in assets}))
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="fresh-adaptive-emission",
            title="Paced adaptive and fifth-region arrival outcomes",
            sample="Two complete saved waveforms and four paced five-minute services",
            boundary="Original IQ at recorded arrival clocks → verified native detector envelopes",
            note=(
                "Queue counts and emission age come from actual raw replay. "
                "Position fitting uses a separate clock."
            ),
            seal="stage-lock.json",
            image=assets[0],
            csv=assets[1],
        ),
    )


def publish(wait):
    from time import monotonic

    deadline = monotonic() + wait
    terminal(REPORT / "prediction-lock.json", deadline)
    rows = sealed(REPORT, "prediction-lock.json", "predictions.jsonl.gz")
    expected = {(case, mode) for case in CPUS for mode in MODES}
    if len(rows) != len(expected) or {(r["id"], r["condition"]) for r in rows} != expected:
        raise ValueError("all six position attempts must retain their denominator")
    source_amendment()
    graph = raw_budget()
    csv_file(REPORT / "raw-budget.csv", graph)
    refs = references(deadline)
    csv_file(REPORT / "scores.csv", positions(rows, refs))
    csv_file(REPORT / "stock-parity.csv", archive_parity(rows))
    cpu = []
    for row in rows:
        use = row.get("position_resources") or {}
        cpu.append(
            dict(
                id=row["id"],
                condition=row["condition"],
                status=row["result"]["status"],
                cpu_s=use.get("cpu_s"),
                wall_s=use.get("wall_s"),
                peak_bytes=use.get("peak_bytes"),
                observations=row["result"]["metrics"].get("observations"),
                tracks=row["result"]["metrics"].get("tracks"),
                raw_verified=row["raw_verified"],
                proved_emissions=row.get("matched_raw_envelopes"),
            )
        )
    csv_file(REPORT / "position-resources.csv", cpu)
    csv_file(
        REPORT / "capture-era-v5.csv",
        [
            dict(
                id=i,
                method=m,
                arm=arm,
                **{k: r["reference"][m][arm].get(k) for k in ("status", "error_km", "rf_rms_hz")},
            )
            for i, r in refs.items()
            for m in ROLES
            for arm in ARMS
        ],
    )
    write(REPORT / "positions.jsonl.gz", compressed_rows(rows))
    figure()
    stage(graph)
    names = (
        "prediction-lock.json",
        "positions.jsonl.gz",
        "raw-budget.csv",
        "scores.csv",
        "stock-parity.csv",
        "position-resources.csv",
        "capture-era-v5.csv",
        "position-runner-audit.json",
        "figure-lock.json",
        "figures.json",
        "stage-lock.json",
        "stage-figure.json",
    )
    save_json(
        REPORT / "score-lock.json",
        dict(
            files={n: _sha(REPORT / n) for n in names},
            exporter_sha256=_sha(Path(__file__)),
            matched_v5_source_sha256=_sha(PARENT / "reference-prediction-lock.json"),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait", type=float, default=0)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.wait)
    if args.plot:
        from .screening_figures import generate

        generate(args.plot, evidence=REPORT)
