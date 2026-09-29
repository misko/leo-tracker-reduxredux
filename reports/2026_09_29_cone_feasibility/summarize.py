"""Verify every receipt and report necessary-condition exclusions honestly."""
# ruff: noqa: E501 -- Keep generated Markdown prose and tables readable.

import itertools

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from study import HERE, bind, read, save, verify


def main():
    plan = read(HERE / "plan.json")
    bindings = read(HERE / "input-seal.json")["sha256"]
    rows, seen, receipts = [], {}, []
    for unit in plan["units"]:
        folder = HERE / "runs" / unit["unit_id"]
        for name, value in read(folder / "seal.json")["sha256"].items():
            assert name not in bindings or bindings[name] == value
            bindings[name] = value
        assert int((folder / "exit-code.txt").read_text()) == 0
        result = read(folder / "result.json")
        assert result["unit_id"] == unit["unit_id"] and result["point_replay_passed"]
        assert len(result["rows"]) == unit["group"]["tracks"]
        assert {r["session_id"] for r in result["rows"]} == set(unit["group"]["session_ids"])
        for row in result["rows"]:
            lo = np.array(row["candidate_lower_bounds_deg"])
            actual = np.array(row["point_candidate_worst_angles_deg"])
            assert lo.shape == actual.shape == (row["candidates"],)
            assert np.isfinite(lo).all() and np.isfinite(actual).all()
            assert np.all((lo >= 0) & (lo <= 180)) and np.all(lo <= actual + 1e-7)
            for width, record in zip(plan["half_angles_deg"], row["widths"], strict=True):
                assert width == record["half_angle_deg"]
                assert record["excluded_candidates"] == int(np.sum(lo > width + 1e-7))
                assert record["track_excluded"] == bool(np.all(lo > width + 1e-7))
                assert record["point_supported_candidates"] == int(np.sum(actual <= width))
                if record["track_excluded"]:
                    assert record["point_supported_candidates"] == 0
            key = row["session_id"], row["track_id"]
            if key in seen:
                np.testing.assert_array_equal(lo, seen[key])
            seen[key] = lo
            if unit["group"]["size"] == 8:
                rows.append({**row, "dataset": unit["group"]["source_dataset"]})
        resource = (folder / "resources.txt").read_text()
        wall = next(
            s.rsplit(": ", 1)[1] for s in resource.splitlines() if "Elapsed (wall clock)" in s
        )
        seconds = 0.0
        for value in wall.split(":"):
            seconds = seconds * 60 + float(value)
        rss = int(
            next(
                s.split(":")[-1] for s in resource.splitlines() if "Maximum resident set size" in s
            )
        )
        assert "Exit status: 0" in resource
        receipts.append({"unit": unit["unit_id"], "wall_seconds": seconds, "peak_rss_kib": rss})
    verify(bindings)
    assert len(plan["units"]) == len(receipts) == 18
    assert len(rows) == len(seen) == 4328
    assert len({(r["session_id"], r["track_id"]) for r in rows}) == len(rows)
    assert len({r["session_id"] for r in rows}) == 72
    aggregates = []
    widths = plan["half_angles_deg"]
    for dataset in ("DS7", "DS8", "DS9"):
        subset = [r for r in rows if r["dataset"] == dataset]
        assert len({r["session_id"] for r in subset}) == 24
        for w0, w1 in itertools.product(widths, repeat=2):
            excluded, unsupported = [], []
            for r in subset:
                record = r["widths"][widths.index((w0, w1)[r["receiver"]])]
                if record["track_excluded"]:
                    excluded.append(r)
                if record["point_supported_candidates"] == 0:
                    unsupported.append(r)
            aggregates.append(
                {
                    "dataset": dataset,
                    "rx0_half_angle_deg": w0,
                    "rx1_half_angle_deg": w1,
                    "tracks": len(subset),
                    "scans": 24,
                    "excluded_tracks": len(excluded),
                    "excluded_scans": len({r["session_id"] for r in excluded}),
                    "point_unsupported_tracks": len(unsupported),
                    "point_unsupported_scans": len({r["session_id"] for r in unsupported}),
                }
            )
    save(
        HERE / "summary.json",
        {
            "aggregates": aggregates,
            "resources": receipts,
            "distinct_scans": 72,
            "distinct_tracks": len(rows),
            "panels_verified": len(receipts),
        },
    )
    equal = [r for r in aggregates if r["rx0_half_angle_deg"] == r["rx1_half_angle_deg"]]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, field, title in zip(
        axes,
        ("excluded_tracks", "excluded_scans"),
        ("Tracks excluded everywhere in search box (%)", "Scans with an excluded track (of 24)"),
        strict=True,
    ):
        data = np.array(
            [
                r[field] * 100 / r["tracks"] if field == "excluded_tracks" else r[field]
                for r in equal
            ]
        ).reshape(3, 4)
        ax.imshow(data, vmin=0, vmax=100 if field == "excluded_tracks" else 24, cmap="OrRd")
        ax.set_xticks(range(4), [f"{w}°" for w in widths])
        ax.set_yticks(range(3), ["DS7", "DS8", "DS9"])
        ax.set_title(title)
        ax.set_xlabel("Equal RX half-angles")
        for i in range(3):
            for j in range(4):
                ax.text(
                    j,
                    i,
                    f"{data[i, j]:.1f}" if field == "excluded_tracks" else str(int(data[i, j])),
                    ha="center",
                    va="center",
                )
    fig.suptitle("Necessary-condition exclusions; remaining cases are unresolved")
    fig.tight_layout()
    for suffix in ("png", "svg"):
        fig.savefig(HERE / f"exclusions.{suffix}", dpi=160)
    plt.close(fig)
    lines = [
        "# Can position or timing changes rescue hard-cone support?",
        "",
        "This completed diagnostic bounds the entire existing E/N ±12 km and timing ±5 s search domain. "
        "It reports tracks for which no retained candidate can satisfy every training observation's cone "
        "anywhere in that domain, under the nominal receiver axes and cached linear interpolation. "
        "It does not fit positions or demonstrate sub-km accuracy.",
        "",
        "A scan with an excluded track cannot have a complete all-track satellite explanation within "
        "these assumptions. Nonexcluded cases remain unresolved; they are not validated feasible solutions. "
        "The bound includes all retained candidates, even those failing a horizon gate. "
        "It is not a full-catalogue impossibility claim or a calibrated beam measurement.",
        "",
        "Main totals use nine nonoverlapping eight-scan panels: 24 distinct scans per dataset. "
        "Nested four-scan panels are independently replayed but not double-counted.",
        "",
        "| Dataset | Half-angle | Excluded tracks / total | Excluded scans / 24 | Unsupported tracks at old fitted point |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in equal:
        lines.append(
            f"| {r['dataset']} | {r['rx0_half_angle_deg']}° | {r['excluded_tracks']}/{r['tracks']} | "
            f"{r['excluded_scans']}/24 | {r['point_unsupported_tracks']} |"
        )
    lines += [
        "",
        "![Domain exclusions](exclusions.png)",
        "",
        "All sixteen RX0/RX1 width pairs are retained in [summary.json](summary.json). "
        "Widths mean half-angles from each axis, distinct from the assumed 20° axis separation.",
        "",
        "The conservative bound subtracts LOS perturbation and receiver-axis rotation from each "
        "timing segment's midpoint angles, takes the worst training observation, then the best segment. "
        "The derivation and numerical margins are fixed in [PROTOCOL.md](PROTOCOL.md). "
        "This is floating-point evaluation of an analytic bound, not formal interval arithmetic.",
        "",
        "All eighteen processes exited zero. Every panel reproduced the earlier nominal point-support "
        "audit; candidate bounds were checked against those actual angles. Duplicate tracks across "
        "nested panels produce identical bounds. Seven synthetic tests cover domain containment, "
        "interior crossings, held isolation, and conservative monotonicity. "
        "Complete input/source and process seals were verified before aggregation.",
        "",
        f"Total child wall time {sum(r['wall_seconds'] for r in receipts):.2f} s; longest "
        f"{max(r['wall_seconds'] for r in receipts):.2f} s; peak RSS "
        f"{max(r['peak_rss_kib'] for r in receipts):,} KiB. No fits, RF collection, waveform reads, "
        "propagation, provider fetches, or production changes.",
        "",
        "Pose, beam shape, cable mapping and satellite associations remain uncalibrated. "
        "Exclusion may indicate an inadequate bank or an incorrect physical assumption; "
        "assigning such a track to background does not restore complete satellite support.",
        "",
        "[Tests](tests.log), [plan](plan.json), [input seal](input-seal.json), "
        "[complete evidence hashes](evidence-sha256.json).",
        "",
    ]
    with (HERE / "README.md").open("x") as f:
        f.write("\n".join(lines))
    bindings.update(
        bind(p for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    )
    save(HERE / "evidence-sha256.json", {"sha256": bindings})
    print({"panels": len(receipts), "scans": 72, "tracks": len(rows), "equal_widths": equal})


if __name__ == "__main__":
    main()
