"""Compare complete archived builds on the frozen four-recording prefix."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from itertools import cycle
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import PLOTS
from tools.pipeline_eval.qualification.score_paired_holdout import elapsed_ratios
from tools.pipeline_eval.scoring import distance_km, distribution

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT.parent / "single-core-2x/measurements"
V3 = "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"
V3_PAIRS = {
    "DS30-0374": "4e86b8d310d00d263bf39082bd621d102c03188320cbcbdcd099316a8c3410a8",
    "DS30-0008": "b2a0a7b73a245731ae2c21bdb3e44664a402397bb65cad6c42b66c8e2989b919",
    "DS30-0155": "e07989fd71164913cc4c4120f5aa45be3d79881d8d3c148b007d85043eba1b00",
    "DS30-0001": "d4fa0e052fdc2ced8b91b22f9b07caee9e0ee418ace7c3bc2f171bbe1610819b",
}
ARMS = ("c0", "fitted_c")


def checked(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Changed source {path}")
    return json.loads(data)


def matched(row, reference, case):
    run, control = (packet["runs"]["candidate"] for packet in (row, reference))
    if (row["cpu"] != reference["cpu"] or row["archive"] != reference["archive"]
            or row["recording"] != reference["recording"] or run["raw_authority"] != case["raw_authority"]
            or control["raw_authority"] != run["raw_authority"]):
        raise ValueError("Different benchmark input or CPU")
    for key, value in (("session_id", case["session"]), ("region", case["region"]),
                       ("window_count", control["receipt"]["window_count"])):
        if control["receipt"][key] != value or run["receipt"][key] != value:
            raise ValueError(f"Different {key}")
    if canonical_digest(row["candidate_specification"]) != row["candidate_specification_digest"]:
        raise ValueError("Invalid candidate specification pin")
    state = run["receipt"]["decision"]
    figures = tuple(obj["name"] for obj in run["artifacts"])
    if state == "complete" and (figures != tuple(PLOTS) or set(run["scientific_digests"]) != {"path", "grid"}):
        raise ValueError("Incomplete publication receipt")
    return run


def sample(row, ref, case, truth, digest):
    run = matched(row, ref, case)
    return dict(case=case["case"], receipt_sha256=digest, elapsed_s=run["elapsed_s"], cpu_s=run["cpu_s"],
                input_blocks=run["input_blocks"], original_run_order=row["order"],
                decision=run["receipt"]["decision"], error_km={arm: distance_km(truth, run["arms"][arm]["latlon"])
                                                              for arm in ARMS},
                rms_hz={arm: run["arms"][arm]["rf_rms_hz"] for arm in ARMS})


def census(publications):
    cases = json.loads((ROOT / "development/stages.json").read_bytes())["stages"]["4"]["cases"]
    if [c["case"] for c in cases] != list(V3_PAIRS):
        raise ValueError("Frozen prefix changed")
    audit = checked(ROOT.parents[1] / "2026_11_21_ds30_full/reference-audit.json",
                    "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5")
    truths = {c["dataset_label"]: (c["reference"]["latitude_deg"], c["reference"]["longitude_deg"])
              for c in audit["cases"] if c["authority_eligible"] and c["sealed_metadata_digests_verified"]}
    samples = defaultdict(dict)
    names = {V3: "ALGO08v3"}
    excluded = {}
    for case in cases:
        key = case["case"]
        ref = checked(publications / key / "pair.json", V3_PAIRS[key])
        if ref["candidate_specification_digest"] != V3:
            raise ValueError("Historical reference differs from installed v3")
        samples[V3][key] = sample(ref, ref, case, truths[key], V3_PAIRS[key])
        for path in sorted(ARCHIVE.glob(f"{key}-*.json")):
            data = path.read_bytes()
            row = json.loads(data)
            spec = row.get("candidate_specification_digest")
            if spec is None or "candidate" not in row.get("runs", {}):
                continue
            if "archive" not in row:
                excluded[path.name] = "No causal orbit archive binding"
                continue
            digest = sha256(data).hexdigest()
            if key in samples[spec]:
                if samples[spec][key]["receipt_sha256"] != digest:
                    raise ValueError(f"Multiple timings for {spec} on {key}; select an order rule first")
                continue
            samples[spec][key] = sample(row, ref, case, truths[key], digest)
            names.setdefault(spec, path.stem.removeprefix(key + "-"))

    complete = {}
    for spec, runs in samples.items():
        if runs.keys() == V3_PAIRS.keys():
            entry = dict(spec=spec, rows=list(runs.values()))
            for field in ("elapsed_s", "cpu_s"):
                pairs = [(samples[V3][key][field], runs[key][field]) for key in V3_PAIRS]
                entry[field] = dict(zip(("median_ratio", "summed_ratio"), elapsed_ratios(pairs), strict=True))
            entry["errors_km"] = {arm: distribution([r["error_km"][arm] for r in runs.values()]) for arm in ARMS}
            complete[names[spec]] = entry
    fastest = [min(method["rows"][i]["elapsed_s"] for method in complete.values()) for i in range(len(cases))]
    v3 = [samples[V3][k]["elapsed_s"] for k in V3_PAIRS]
    return dict(builds=complete, excluded=excluded, incomplete_coverage={names[s]: list(rows) for s, rows in samples.items()
                                                       if rows.keys() != V3_PAIRS.keys()},
                fastest_complete_build_per_recording_elapsed_ratios=elapsed_ratios(list(zip(v3, fastest, strict=True))))


def plot(builds, path):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.8), layout="constrained")
    limit = 1.06 * max(row["error_km"][arm] for build in builds.values() for row in build["rows"]
                       for arm in ARMS if row["error_km"][arm] is not None)
    styles = cycle(zip(("#283e60", "#a35209", "#24745b", "#76528e"), ("o", "^", "s", "D"),
                       ("-", "--", "-.", ":"), (66, 47, 33, 17)))
    for name, build in builds.items():
        color, marker, line, size = next(styles)
        for i, (row, ref) in enumerate(zip(build["rows"], builds["ALGO08v3"]["rows"], strict=True)):
            axes[0].scatter(i, row["elapsed_s"]/ref["elapsed_s"], s=39, marker=marker, color=color,
                            label=name if i == 0 else None)
        for ax, arm in zip(axes[1:], ARMS):
            errors = sorted(r["error_km"][arm] for r in build["rows"] if r["error_km"][arm] is not None)
            x = [0, *errors, limit]
            y = [0, *(100*(j+1)/len(build["rows"]) for j in range(len(errors))), 100*len(errors)/len(build["rows"])]
            ax.step(x, y, where="post", color=color, lw=1.5, linestyle=line)
            ax.scatter(errors, y[1:-1], edgecolor=color, facecolor="none", marker=marker, s=size)
    axes[0].axhline(.5, linestyle="--", color="0.4")
    axes[0].set(xticks=list(range(4)), xticklabels=[key[-4:] for key in V3_PAIRS], xlabel="DS30 recording",
                ylabel="Elapsed time / ALGO08v3", ylim=(0, None))
    for ax, title in zip(axes[1:], ("Fixed c = 0", "Fitted c")):
        ax.set(title=title, xlabel="Horizontal error (km)", xlim=(0, limit), ylim=(-3, 105), yticks=[0, 25, 50, 75, 100])
    axes[1].set_ylabel("All four recordings (%)")
    for ax in axes:
        ax.grid(alpha=.2)
    fig.suptitle("Archived complete publications on the first four DS30 assignments")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="outside lower center", ncols=4, frameon=False)
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("publications", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    summary = census(args.publications)
    args.output.mkdir(exist_ok=True, parents=True)
    (args.output / "archived-four.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    plot(summary["builds"], args.output / "archived-four.png")
