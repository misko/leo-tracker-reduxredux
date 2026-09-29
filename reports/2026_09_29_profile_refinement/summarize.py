"""Audit stored joint endpoints and report training-only promotion outcomes."""
# ruff: noqa: E501 -- Markdown report prose and tables.

import math

import matplotlib
import numpy as np
from study import HERE, PRIOR, ROOT, digest, read, save, verify

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main():
    bindings = read(HERE / "input-seal.json")["sha256"]
    plan = read(HERE / "plan.json")
    refpath = HERE.parent / "2026_09_29_drift_geographic/all-complete/summary.json"
    inventory = read(refpath.parents[1] / "evidence-sha256.json")["sha256"]
    refname = str(refpath.relative_to(ROOT))
    assert digest(refpath) == inventory[refname]
    bindings[refname] = inventory[refname]
    reference = read(refpath)["reference"]

    def distance(coords):
        a, b, c, d = map(math.radians, [*reference, *coords])
        h = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
        return 2 * 6371008.8 * math.asin(math.sqrt(min(1, h)))

    panels = []
    for u in plan["units"]:
        folder = HERE / "runs" / u["unit_id"]
        assert read(folder / "exit.json")["exit_code"] == 0
        for n, h in read(folder / "seal.json")["sha256"].items():
            assert n not in bindings or bindings[n] == h
            bindings[n] = h
        r = read(folder / "result.json")
        old = read(ROOT / u["baseline_held"])
        selection = read(ROOT / u["selection"])["selected"]
        oldcoords = [selection["estimate"][k] for k in ("latitude_deg", "longitude_deg")]
        assert r["center"] == u["x"] == selection["x"]
        assert abs(r["center_score"] - old["training_log_score"]) < 1e-7
        assert abs(r["center_held_score"] - old["held_log_score"]) < 1e-7
        probes = read(PRIOR / "runs" / u["unit_id"] / "result.json")["profiles"]
        assert len(r["results"]) == 2
        rows = []
        for radius, fit in zip((0.25, 1.0), r["results"], strict=True):
            candidates = [p for p in probes if p["qualified"] and p["radius_km"] == radius]
            chosen = max(candidates, key=lambda p: p["score"])
            assert fit["initial"] == chosen["position"] + chosen["selected"]["timing"]
            limits = [12, 12] + [5] * len(u["group"]["session_ids"])
            bound = any(limit - abs(v) < 0.001 for limit, v in zip(limits, fit["x"], strict=True))
            assert bound == fit["boundary"]
            assert len(fit["checks"]) == 2 * len(fit["x"])
            agreement = []
            for axis in range(len(fit["x"])):
                a, b = fit["checks"][2 * axis : 2 * axis + 2]
                assert [a["step"], b["step"]] == (
                    [0.0005, 0.00025] if axis < 2 else [0.0000625, 0.00003125]
                )
                for c in (a, b):
                    assert c["axis"] == axis
                    assert (
                        abs(c["difference"] - abs(c["numerical"] - fit["gradient"][axis])) < 1e-12
                    )
                    z = fit["x"][axis]
                    step = c["step"]
                    crossing = axis >= 2 and math.floor((z - step) * 4) != math.floor(
                        (z + step) * 4
                    )
                    assert crossing == c["crosses_node"]
                agreement.append(abs(a["numerical"] - b["numerical"]))
            assert agreement == fit["step_agreement"]
            qualified = (
                fit["success"]
                and not bound
                and max(map(abs, fit["gradient"])) <= 0.01
                and all(c["difference"] < 0.002 and not c["crosses_node"] for c in fit["checks"])
                and max(agreement) < 0.002
            )
            assert qualified == fit["qualified"]
            assert (
                abs(sum(t["held_log_score"] for t in fit["held_rows"]) - fit["held_score"]) < 1e-7
            )
            assert abs(sum(t["training_log_score"] for t in fit["held_rows"]) - fit["score"]) < 1e-7
            assert abs(fit["training_delta"] - (fit["score"] - r["center_score"])) < 1e-9
            assert abs(fit["held_delta"] - (fit["held_score"] - r["center_held_score"])) < 1e-9
            separation = 1000 * float(np.linalg.norm(np.asarray(fit["x"][:2]) - u["x"][:2]))
            assert abs(separation - fit["center_distance_m"]) < 1e-9
            tv = []
            maps = 0
            signal = []
            for before, after in zip(old["rows"], fit["held_rows"], strict=True):
                assert (before["session_id"], before["track_id"]) == (
                    after["session_id"],
                    after["track_id"],
                )
                a = np.asarray(before["weights_given_signal"])
                b = np.asarray(after["weights_given_signal"])
                assert a.shape == b.shape and abs(sum(b) - 1) < 1e-8 and min(b) >= 0
                tv.append(float(np.sum(abs(a - b))) / 2)
                maps += int(np.argmax(a) != np.argmax(b))
                signal.append(abs(before["signal_responsibility"] - after["signal_responsibility"]))
            rows.append(
                dict(
                    radius_km=radius,
                    qualified=qualified,
                    training_delta=fit["training_delta"],
                    held_delta=fit["held_delta"],
                    distance_m=separation,
                    error_m=distance(fit["coordinates"]),
                    max_timing_change_s=max(
                        abs(a - b) for a, b in zip(fit["x"][2:], u["x"][2:], strict=True)
                    ),
                    candidate_map_changes=maps,
                    tracks=len(tv),
                    mean_conditional_candidate_tv=float(np.mean(tv)),
                    mean_signal_responsibility_change=float(np.mean(signal)),
                )
            )
        eligible = [x for x in rows if x["qualified"] and x["training_delta"] > 1e-6]
        winner = max(eligible, key=lambda x: x["training_delta"]) if eligible else None
        panels.append(
            dict(
                unit_id=u["unit_id"],
                baseline_error_m=distance(oldcoords),
                results=rows,
                selected_radius_km=winner["radius_km"] if winner else None,
                selected_error_m=winner["error_m"] if winner else distance(oldcoords),
                selected_held_delta=winner["held_delta"] if winner else 0,
            )
        )
    verify(bindings)
    out = dict(audit_passed=True, reference=reference, panels=panels)
    save(HERE / "summary.json", out)
    lines = [
        "# Joint refinement from spatial-profile alternatives",
        "",
        "All eighteen panels completed. Starts were selected by training score at each of two radii; held scores and reference errors never selected starts or winners.",
        "",
        "| Panel | Start radius (km) | Qualified | Training change (nats) | Held change (nats) | Shift (m) | Nominal error (m) |",
        "|---|---:|---|---:|---:|---:|---:|",
    ]
    for p in panels:
        for r in p["results"]:
            lines.append(
                f"| {p['unit_id']} | {r['radius_km']} | {r['qualified']} | {r['training_delta']:+.6f} | {r['held_delta']:+.3f} | {r['distance_m']:.2f} | {r['error_m']:.1f} |"
            )
    lines += [
        "",
        "## Training-selected outcomes",
        "",
        "Retain the original result unless a qualified endpoint improves training score by more than 1e-6 nats. Errors below are medians of three early/middle/late sets, in metres. These are exposed unsurveyed-reference errors, not blind accuracy or calibrated resolution.",
        "",
        "| Dataset | Scans per set | Original median | Refined median |",
        "|---|---:|---:|---:|",
    ]
    for ds in ("DS7", "DS8", "DS9"):
        for size in (4, 8):
            pp = [
                p
                for p in panels
                if p["unit_id"].startswith(ds) and p["unit_id"].endswith("_" + str(size))
            ]
            assert len(pp) == 3
            lines.append(
                f"| {ds} | {size} | {np.median([p['baseline_error_m'] for p in pp]):.1f} | {np.median([p['selected_error_m'] for p in pp]):.1f} |"
            )
    lines += [
        "",
        "![Training-selected errors and all endpoint shifts](refinement.png)",
        "",
        "The summary retains candidate MAP changes, conditional candidate-weight total variation, signal-responsibility changes and maximum timing changes. These describe model assignments, not independently verified satellite identities.",
        "",
        "The auditor rechecks source/input/process hashes, start selection, qualification gates, derivative arithmetic, training/held sums, track correspondence and probability normalization. It does not independently reimplement the radio likelihood. Five prelaunch tests passed; no retries or changed scientific sources. Full execution resources and failures are retained per panel.",
        "",
        "[Protocol](PROTOCOL.md), [summary](summary.json), [tests](tests.log), [complete evidence](evidence-sha256.json).",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), layout="constrained")
    x = np.arange(18)
    axes[0].plot(x, [p["baseline_error_m"] for p in panels], "o-", label="Original")
    axes[0].plot(
        x, [p["selected_error_m"] for p in panels], "x--", label="Training-selected refinement"
    )
    axes[0].axhline(1000, color="grey", linestyle=":")
    axes[0].set_ylabel("Nominal reference error (m)")
    axes[0].legend()
    axes[0].set_xticks(x, [p["unit_id"].replace("_", " ") for p in panels], rotation=65, ha="right")
    for j, radius in enumerate((0.25, 1.0)):
        rows = [p["results"][j] for p in panels]
        axes[1].scatter(
            [r["distance_m"] for r in rows],
            [r["training_delta"] for r in rows],
            label=f"{radius} km start",
        )
    axes[1].set_xlabel("Endpoint separation from original fit (m)")
    axes[1].set_ylabel("Training-score change (nats)")
    axes[1].legend()
    fig.suptitle("Joint location/timing refinement — finite starts, uncalibrated reference")
    for suffix in ("png", "svg"):
        fig.savefig(HERE / ("refinement." + suffix), dpi=160)
    plt.close(fig)
    for p in HERE.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts and p.name != "evidence-sha256.json":
            bindings[str(p.relative_to(ROOT))] = digest(p)
    save(HERE / "evidence-sha256.json", dict(sha256=bindings))
    print(
        "Audited",
        len(panels),
        "panels;",
        sum(r["qualified"] for p in panels for r in p["results"]),
        "qualified endpoints",
        flush=True,
    )


if __name__ == "__main__":
    main()
