"""Reconstruct training selections and numerical gates before reporting error."""
# ruff: noqa: E501 -- Markdown report prose and rows.

import math
import sys

import numpy as np
from study import HERE, ROOT, digest, read, save, verify


def main(label):
    plan = read(HERE / "plan.json")
    bindings = read(HERE / "input-seal.json")["sha256"]
    terminal = set()
    for path in (HERE / "runs").glob("**/seal.json"):
        terminal.add(path.parent)
        for name, value in read(path)["sha256"].items():
            assert name not in bindings or bindings[name] == value
            bindings[name] = value
    verify(bindings)
    base = HERE.parent / "2026_09_29_consecutive_panels"
    original_path = base / "plan.json"
    original = read(original_path)
    evidence = read(base / "evidence-sha256.json")
    evidence = evidence.get("sha256", evidence)
    assert evidence[str(original_path.relative_to(ROOT))] == digest(original_path)
    bindings[str(original_path.relative_to(ROOT))] = digest(original_path)
    references = set()
    for members in original["membership"].values():
        for m in members:
            p = ROOT / m["pose_path"]
            assert digest(p) == m["pose_sha256"]
            bindings[m["pose_path"]] = digest(p)
            pose = read(p)["pose_authority"]
            references.add((pose["latitude_deg"], pose["longitude_deg"]))
    assert len(references) == 1
    reference = next(iter(references))

    def distance(estimate):
        a, b, c, d = map(
            math.radians, (*reference, estimate["latitude_deg"], estimate["longitude_deg"])
        )
        h = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
        result = 2 * 6371008.8 * math.asin(math.sqrt(min(1, h)))
        u = np.array([math.cos(a) * math.cos(b), math.cos(a) * math.sin(b), math.sin(a)])
        v = np.array([math.cos(c) * math.cos(d), math.cos(c) * math.sin(d), math.sin(c)])
        assert (
            abs(
                result - 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(u, v))), float(u @ v))
            )
            < 1e-4
        )
        return result

    rows = []
    for u in plan["units"]:
        parent = HERE / "runs" / u["unit_id"]
        row = dict(
            unit_id=u["unit_id"],
            arm=u["arm"],
            dataset=u["base_unit_id"][:3],
            size=u["group"]["size"],
            status="Pending",
        )
        if not (parent / "selection.json").exists():
            rows.append(row)
            continue
        selection = read(parent / "selection.json")
        eligible, starts = [], []
        for start, stored in zip(u["starts"], selection["runs"], strict=True):
            folder = parent / "fit" / start["name"]
            assert folder in terminal
            code = read(folder / "exit.json")["exit_code"]
            result = read(folder / "result.json") if code == 0 else None
            assert result == stored
            if result:
                assert result["initial"] == start["x"]
                assert result["unit_id"] == u["unit_id"]
                qualified = (
                    result["success"]
                    and max(map(abs, result["gradient"])) <= 0.01
                    and all(
                        min(abs(x - b), abs(x + b)) >= 0.001
                        for x, b in zip(result["x"], [12, 12] + [5] * row["size"], strict=True)
                    )
                )
                assert qualified == result["qualified"]
                if qualified:
                    eligible.append(result)
            starts.append(dict(name=start["name"], exit_code=code, result=result))
        chosen = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
        assert chosen == selection["selected"] and len(eligible) == selection["qualified_starts"]
        row.update(starts=starts, qualified_starts=len(eligible))
        if chosen is None:
            row["status"] = "No qualified start"
            rows.append(row)
            continue
        if parent / "held" not in terminal:
            rows.append(row)
            continue
        code = read(parent / "held/exit.json")["exit_code"]
        row["status"] = "Held process failed"
        if code:
            rows.append(row)
            continue
        held = read(parent / "held/result.json")
        checks = held["gradient_checks"]
        assert len(checks) == 2 * (2 + row["size"])
        assert [c["axis"] for c in checks] == [a for a in range(2 + row["size"]) for _ in range(2)]
        assert [c["step"] for c in checks] == [0.001, 0.0005] * 2 + [0.0000625, 0.00003125] * row[
            "size"
        ]
        for c in checks:
            assert c["absolute_difference"] == abs(c["numerical"] - held["gradient"][c["axis"]])
            axis, step = c["axis"], c["step"]
            crossing = axis >= 2 and math.floor((chosen["x"][axis] - step) * 4) != math.floor(
                (chosen["x"][axis] + step) * 4
            )
            assert crossing == c["crosses_grid_node"]
        agreement = [
            abs(checks[2 * a]["numerical"] - checks[2 * a + 1]["numerical"])
            for a in range(2, 2 + row["size"])
        ]
        assert agreement == held["timing_step_agreement"]
        passed = (
            abs(held["training_log_score"] - chosen["training_log_score"]) < 1e-7
            and held["old_position_replay_error"] < 1e-7
            and all(c["absolute_difference"] < 0.002 and not c["crosses_grid_node"] for c in checks)
            and all(v < 0.002 for v in agreement)
        )
        assert passed == held["audit_passed"]
        assert len(held["rows"]) == u["group"]["tracks"]
        assert abs(sum(r["held_log_score"] for r in held["rows"]) - held["held_log_score"]) < 1e-7
        old = read(ROOT / u["selection"])["selected"]
        old_held = read(ROOT / u["baseline_held"])
        row.update(
            status="Audited" if passed else "Audit failed",
            selected_start=chosen["start_id"],
            error_m=distance(chosen["estimate"]),
            baseline_error_m=distance(old["estimate"]),
            held_delta_nats=held["held_log_score"] - old_held["held_log_score"],
        )
        rows.append(row)
    medians = {}
    for arm in ("symmetric", "rx0_anchor", "rx1_anchor"):
        medians[arm] = {}
        for ds in ("DS7", "DS8", "DS9"):
            medians[arm][ds] = {}
            for size in (4, 8):
                selected = [
                    r for r in rows if r["arm"] == arm and r["dataset"] == ds and r["size"] == size
                ]
                medians[arm][ds][size] = (
                    float(np.median([r["error_m"] for r in selected]))
                    if all(r["status"] == "Audited" for r in selected)
                    else None
                )
    folder = HERE / label
    folder.mkdir(exist_ok=False)
    save(folder / "summary.json", dict(reference=reference, rows=rows, medians_m=medians))
    lines = [
        "# Differential-drift geographic checkpoint",
        "",
        "All 54 arm/panel combinations remain in scope. Pending and failed audits do not count as successful fits.",
        "The exposed reference is unsurveyed; errors are descriptive, not blind accuracy or calibrated resolution.",
        "",
        "| Unit | Status | Error m | Baseline m | Held Δnats | Qualified starts |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        vals = [
            f"{r[k]:.2f}" if k in r else "—"
            for k in ("error_m", "baseline_error_m", "held_delta_nats")
        ]
        lines.append(
            f"| {r['unit_id']} | {r['status']} | {' | '.join(vals)} | {r.get('qualified_starts', '—')} |"
        )
    lines += [
        "",
        "[All starts, outcomes and medians](summary.json). Failed-audit coordinates remain visible but unvalidated.",
    ]
    (folder / "README.md").write_text("\n".join(lines) + "\n")
    bindings[str((HERE / "summarize.py").relative_to(ROOT))] = digest(HERE / "summarize.py")
    for p in folder.iterdir():
        bindings[str(p.relative_to(ROOT))] = digest(p)
    save(folder / "seal.json", {"sha256": bindings})
    print(
        {
            status: sum(r["status"] == status for r in rows)
            for status in sorted({r["status"] for r in rows})
        }
    )


if __name__ == "__main__":
    main(sys.argv[1])
