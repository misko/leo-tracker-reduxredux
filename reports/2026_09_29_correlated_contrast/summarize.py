"""Reconstruct selections and audits; retain pending units in bounded checkpoints."""
# ruff: noqa: E501 -- Report prose and Markdown tables.

import math
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from study import BASE, CONE, HERE, ROOT, TREND, digest, read, save, verify


def main(label):
    plan = read(HERE / "plan.json")
    bindings = read(HERE / "input-seal.json")["sha256"]

    def merge(values):
        for name, value in values.items():
            assert name not in bindings or bindings[name] == value, name
            bindings[name] = value

    seals = list((HERE / "runs").glob("**/seal.json"))
    terminal_folders = {seal.parent for seal in seals}
    for seal in seals:
        merge(read(seal)["sha256"])
    verify(bindings)

    def bound(path):
        name = str(path.relative_to(ROOT))
        report = ROOT.joinpath(*path.relative_to(ROOT).parts[:2])
        inventory = read(report / "evidence-sha256.json")
        inventory = inventory.get("sha256", inventory)
        assert inventory[name] == digest(path), name
        merge({name: digest(path)})
        return read(path)

    original = bound(BASE / "plan.json")
    refs = set()
    for members in original["membership"].values():
        for member in members:
            path = ROOT / member["pose_path"]
            assert digest(path) == member["pose_sha256"]
            merge({str(path.relative_to(ROOT)): digest(path)})
            pose = read(path)["pose_authority"]
            refs.add((pose["latitude_deg"], pose["longitude_deg"]))
    assert len(refs) == 1
    reference = next(iter(refs))

    def distance(estimate):
        a, b, c, d = map(
            math.radians, (*reference, estimate["latitude_deg"], estimate["longitude_deg"])
        )
        h = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
        value = 2 * 6371008.8 * math.asin(math.sqrt(min(1, h)))
        u = np.array([math.cos(a) * math.cos(b), math.cos(a) * math.sin(b), math.sin(a)])
        v = np.array([math.cos(c) * math.cos(d), math.cos(c) * math.sin(d), math.sin(c)])
        assert (
            abs(value - 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(u, v))), float(u @ v)))
            < 1e-4
        )
        return value

    rows, resources = [], []
    for unit, group in zip(plan["units"], plan["groups"], strict=True):
        parent = HERE / "runs" / unit["unit_id"]
        ready = (parent / "selection.json").exists() and all(
            parent / "fit" / start["source_dataset"] in terminal_folders for start in unit["starts"]
        )
        if ready and read(parent / "selection.json")["selected"] is not None:
            ready = parent / "held" in terminal_folders
        if not ready:
            rows.append(
                {
                    "unit": unit["unit_id"],
                    "status": "Pending",
                    "arm": unit["arm"],
                    "dataset": group["source_dataset"],
                    "size": group["size"],
                }
            )
            continue
        selection = read(parent / "selection.json")
        eligible = []
        for start, stored in zip(unit["starts"], selection["runs"], strict=True):
            folder = parent / "fit" / start["source_dataset"]
            code = int((folder / "exit-code.txt").read_text())
            result = read(folder / "result.json") if code == 0 else None
            assert result == stored
            if result:
                assert (
                    result["initial"] == start["x"]
                    and result["session_ids"] == group["session_ids"]
                )
                qualified = bool(
                    result["success"]
                    and max(map(abs, result["gradient"])) <= 0.01
                    and all(
                        min(abs(x - b), abs(x + b)) >= 0.001
                        for x, b in zip(result["x"], [12, 12] + [5] * group["size"], strict=True)
                    )
                )
                assert qualified == result["qualified"]
                if qualified:
                    eligible.append(result)
        chosen = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
        assert chosen == selection["selected"] and len(eligible) == selection["qualified_starts"]
        generic = [r for r in eligible if r["start_id"] != "no_cone"]
        generic = max(generic, key=lambda r: r["training_log_score"]) if generic else None
        held = read(parent / "held/result.json") if (parent / "held/result.json").exists() else None
        valid = False
        if held:
            assert chosen is not None and int((parent / "held/exit-code.txt").read_text()) == 0
            assert held["session_ids"] == group["session_ids"]
            checks = held["gradient_checks"]
            assert len(checks) == 2 * (2 + group["size"])
            assert [c["axis"] for c in checks] == [
                a for a in range(2 + group["size"]) for _ in range(2)
            ]
            assert [c["step"] for c in checks] == [0.001, 0.0005] * 2 + [
                0.0000625,
                0.00003125,
            ] * group["size"]
            for c in checks:
                assert c["absolute_difference"] == abs(c["numerical"] - c["implemented"])
                assert c["implemented"] == held["full_training_gradient"][c["axis"]]
                crossing = c["axis"] >= 2 and math.floor(
                    (chosen["x"][c["axis"]] - c["step"]) * 4
                ) != math.floor((chosen["x"][c["axis"]] + c["step"]) * 4)
                assert bool(crossing) == c["crosses_grid_node"]
            agreements = [
                abs(checks[2 * a]["numerical"] - checks[2 * a + 1]["numerical"])
                for a in range(2, 2 + group["size"])
            ]
            assert agreements == held["timing_step_agreement"]
            valid = (
                abs(held["training_log_score"] - chosen["training_log_score"]) < 1e-7
                and all(
                    c["absolute_difference"] < 0.002 and not c["crosses_grid_node"] for c in checks
                )
                and all(v < 0.002 for v in agreements)
                and all(v < 1e-7 for v in held["zero_decay_replay"].values())
            )
            assert valid == held["audit_passed"]
            assert len(held["rows"]) == group["tracks"]
            assert sum(r["held_observations"] for r in held["rows"]) == group["held_observations"]
            assert (
                abs(sum(r["held_log_score"] for r in held["rows"]) - held["held_log_score"]) < 1e-7
            )
        donor = (
            TREND / "runs" / (unit["base_unit_id"] + "_q020")
            if unit["half_angle_deg"] is None
            else CONE / "runs" / (unit["base_unit_id"] + "_c40")
        )
        old = bound(donor / "selection.json")["selected"]
        oldheld = bound(donor / "held/result.json")
        assert oldheld["audit_passed"] and old["session_ids"] == group["session_ids"]
        if held:
            assert [
                (r["session_id"], r["track_id"], r["held_observations"]) for r in held["rows"]
            ] == [(r["session_id"], r["track_id"], r["held_observations"]) for r in oldheld["rows"]]
        rows.append(
            {
                "unit": unit["unit_id"],
                "arm": unit["arm"],
                "dataset": group["source_dataset"],
                "size": group["size"],
                "status": "Pass" if valid else "Failed audit" if chosen else "No qualified fit",
                "qualified_starts": len(eligible),
                "error_m": distance(chosen["estimate"]) if chosen else None,
                "baseline_error_m": distance(old["estimate"]),
                "generic_only_error_m": distance(generic["estimate"]) if generic else None,
                "generic_only_score_gap": chosen["training_log_score"]
                - generic["training_log_score"]
                if generic
                else None,
                "held_change_nats": held["held_log_score"] - oldheld["held_log_score"]
                if held
                else None,
                "selected": chosen,
                "audit": held,
            }
        )
    for f in sorted(folder / "resources.txt" for folder in terminal_folders):
        text = f.read_text()
        elapsed = next(
            line.rsplit(": ", 1)[1] for line in text.splitlines() if "Elapsed (wall clock)" in line
        )
        seconds = 0.0
        for part in elapsed.split(":"):
            seconds = seconds * 60 + float(part)
        resources.append(
            {
                "path": str(f.relative_to(ROOT)),
                "wall_seconds": seconds,
                "peak_rss_kib": int(
                    next(
                        line.rsplit(":", 1)[1]
                        for line in text.splitlines()
                        if "Maximum resident set size" in line
                    )
                ),
                "exit_code": int((f.parent / "exit-code.txt").read_text()),
            }
        )
    complete = [r for r in rows if r["status"] != "Pending"]
    valid = [r for r in rows if r["status"] == "Pass"]
    aggregates = []
    for arm in ("corr10", "corr10_c40"):
        for ds in ("DS7", "DS8", "DS9"):
            for size in (4, 8):
                subset = [
                    r for r in rows if r["arm"] == arm and r["dataset"] == ds and r["size"] == size
                ]
                assert len(subset) == 3
                aggregates.append(
                    {
                        "arm": arm,
                        "dataset": ds,
                        "size": size,
                        "passed": sum(r["status"] == "Pass" for r in subset),
                        "median_error_m": float(np.median([r["error_m"] for r in subset]))
                        if all(r["status"] == "Pass" for r in subset)
                        else None,
                    }
                )
    output = HERE / label
    output.mkdir(exist_ok=False)
    save(
        output / "summary.json",
        {"rows": rows, "aggregates": aggregates, "resources": resources, "reference": reference},
    )
    lines = [
        "# Correlated contrast localization",
        "",
        f"Completed {len(complete)}/36 planned units; selected numerical audits pass for {len(valid)}/{len(complete)} completed units. "
        "Pending and failed units remain explicit. No blanket sub-km claim follows.",
        "",
        "Errors are horizontal metres to the exposed unsurveyed reference. The comparison changes correlation in both "
        "satellite and background contrast densities. corr10 compares with published q020; corr10_c40 compares with published soft40. "
        "Position and one timing per scan are fitted using training data only.",
        "",
        "| Arm | Dataset | Scans | Passed blocks | Median error (m) |",
        "|---|---|---:|---:|---:|",
    ]
    for a in aggregates:
        value = f"{a['median_error_m']:.1f}" if a["median_error_m"] is not None else "Incomplete"
        lines.append(f"| {a['arm']} | {a['dataset']} | {a['size']} | {a['passed']}/3 | {value} |")
    lines += [
        "",
        "| Panel / arm | Status | Qualified starts | Error (m) | Matched baseline (m) | Held change (nats) |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        if r["status"] == "Pending":
            lines.append(f"| {r['unit']} | Pending | — | — | — | — |")
            continue
        error = f"{r['error_m']:.1f}" if r["error_m"] is not None else "—"
        delta = f"{r['held_change_nats']:+.3f}" if r["held_change_nats"] is not None else "—"
        lines.append(
            f"| {r['unit']} | {r['status']} | {r['qualified_starts']}/4 | {error} | {r['baseline_error_m']:.1f} | {delta} |"
        )
    lines += [
        "",
        f"Among audited comparisons, {sum(r['error_m'] < r['baseline_error_m'] for r in valid)}/{len(valid)} have lower nominal geographic error; "
        f"{sum(r['held_change_nats'] > 0 for r in valid)}/{len(valid)} improve held prediction. These are dependent explored panels, not independent trials.",
        "",
        f"{len(resources)} child receipts: {sum(r['wall_seconds'] for r in resources):.2f} seconds summed wall time; "
        f"peak RSS {max((r['peak_rss_kib'] for r in resources), default=0):,} KiB. "
        f"Nonzero child exits: {sum(r['exit_code'] != 0 for r in resources)}. No completed fits were retried.",
        "",
        "Ten prelaunch tests pass. The summarizer reconstructs qualification, training selection and all derivative gates; "
        "zero-decay replays and matching observation identities are checked. Generic-only selections and every selected audit "
        "remain in summary.json. Local convergence does not prove a global optimum or correct satellite identity.",
        "",
        "The inherited origin is already 809 m from the reference. Neither nominal sub-km errors nor higher held frequency density "
        "establish surveyed accuracy, calibrated uncertainty or unseen-site transfer. No new RF, IQ processing, propagation or production changes.",
        "",
        "![Audited matched errors](comparison.png)",
        "",
        "[Protocol](../PROTOCOL.md), [tests](../tests.log), [full results](summary.json).",
        "",
    ]
    (output / "README.md").write_text("\n".join(lines))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, arm in zip(axes, ("corr10", "corr10_c40"), strict=True):
        for ds in ("DS7", "DS8", "DS9"):
            subset = [r for r in valid if r["arm"] == arm and r["dataset"] == ds]
            ax.scatter(
                [r["baseline_error_m"] for r in subset], [r["error_m"] for r in subset], label=ds
            )
        ax.plot([0, 5000], [0, 5000], color="gray", linestyle="--")
        ax.axhline(1000, color="gray", alpha=0.4)
        ax.axvline(1000, color="gray", alpha=0.4)
        ax.set(xlabel="Matched zero-correlation error (m)", ylabel="New error (m)", title=arm)
        ax.legend()
        ax.grid(alpha=0.2)
    fig.suptitle(
        f"Audited results: {len(valid)}/{len(complete)} completed, {36 - len(complete)} pending"
    )
    fig.tight_layout()
    for suffix in ("png", "svg"):
        fig.savefig(output / f"comparison.{suffix}", dpi=160)
    plt.close(fig)
    paths = list(output.iterdir()) + [HERE / "summarize.py", HERE / "input-seal.json"] + seals
    paths += [HERE / "runs" / r["unit"] / "selection.json" for r in complete]
    bindings.update({str(p.relative_to(ROOT)): digest(p) for p in paths if p.is_file()})
    save(output / "evidence-sha256.json", {"sha256": bindings})
    print({"completed": len(complete), "audited": len(valid), "aggregates": aggregates}, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
