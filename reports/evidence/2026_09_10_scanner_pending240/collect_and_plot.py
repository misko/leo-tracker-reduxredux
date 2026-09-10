"""Archive original receipts and plot the paired SDK experiment, without RF."""

import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUN = Path("/tmp/leo-pending240.nd2ckj")
ARM = Path("/tmp/leo-pending240-arm.X6O6Kw")
FIGURES = REPO / "reports/figures/2026_09_10_scanner_pending240"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(path, name):
    data = path.read_bytes()
    target = HERE / (name + ".gz")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = gzip.compress(data, mtime=0)
    if target.exists():
        assert target.read_bytes() == payload, "original receipt changed"
    else:
        with target.open("xb") as stream:
            stream.write(payload)
    return dict(
        path=str(target.relative_to(HERE)),
        original_sha256=sha(data),
        original_bytes=len(data),
        archive_sha256=sha(payload),
    )


def main():
    receipt = json.loads((RUN / "replays/receipt.json").read_bytes())
    assert receipt["completed"] and len(receipt["cases"]) == 42
    originals = [archive(RUN / "replays/receipt.json", "replay-receipt.json")]
    for name, expected in receipt["sources"].items():
        snapshot = HERE / "sources" / (name + ".gz")
        data = (
            gzip.decompress(snapshot.read_bytes())
            if snapshot.exists()
            else (REPO / name).read_bytes()
        )
        assert sha(data) == expected
        if not snapshot.exists():
            originals.append(archive(REPO / name, "sources/" + name))
        else:
            originals.append(
                dict(
                    path=str(snapshot.relative_to(HERE)),
                    original_sha256=expected,
                    original_bytes=len(data),
                    archive_sha256=sha(snapshot.read_bytes()),
                )
            )
    for case in receipt["cases"]:
        path = RUN / "replays" / case["path"]
        assert sha(path.read_bytes()) == case["sha256"]
        result = json.loads(path.read_bytes())
        actual = result["actual"]
        assert result["sampled_model"]["exact_dispatch_agreement"]
        assert actual["records"] == actual["visits"]
        assert not actual["starved_targets"]
        assert not actual["protection"]["disabled"]
        assert actual["protection"]["peak_occupied_slots"] <= 3
        originals.append(archive(path, "replays/" + path.parent.name + ".json"))
    for name, count in (("sdk-regression.xml", 738), ("provider-config.xml", 47)):
        suite = ET.fromstring((RUN / name).read_bytes()).find("testsuite")
        assert int(suite.get("tests")) == count
        assert all(suite.get(k) == "0" for k in ("failures", "errors", "skipped"))
    names = [
        "sdk-regression.xml",
        "provider-config.xml",
        "radio-preflight.json",
        "run_provider.py",
        "delayed-test_scanner_glrt_provider.log",
        "delayed-receipt.json",
        "asan-receipt.json",
    ]
    names += [
        f"v2-{mode}-{suffix}"
        for mode in ("delayed", "asan")
        for suffix in (
            "configure.log",
            "build.log",
            "test_scanner_glrt_provider.log",
            "test_spf_hop_adaptive_native.log",
            "test_spf_hop_adaptive_policy.log",
        )
    ]
    for name in names:
        originals.append(archive(RUN / name, "provider/" + name))
    for name in ("sdk.so.build.json", "worker.build.json"):
        originals.append(archive(RUN / "replays/build" / name, "build/" + name))
    # Exact hardware-stage receipts are evidence only when present; never label
    # a cross-build as ARM execution. The report and tests inspect this flag.
    arm_passed = (ARM / "arm-provider-result.json").exists()
    if arm_passed:
        assert (ARM / "arm-postflight.json").exists()
        result = json.loads((ARM / "arm-provider-result.json").read_bytes())
        assert (
            "both rates, real worker, delayed events, terminal drain and exact-gap tests passed"
            in result["output"]
        )
    for name in (
        "receipt.json",
        "build_bundle.py",
        "run_arm_provider.py",
        "configure.json",
        "compile.json",
        "arm-preflight.json",
        "arm-provider-result.json",
        "arm-provider-failure.json",
        "arm-postflight.json",
        "release/bundle.json",
        "release/configuration.json",
        "release/algorithm.json",
    ):
        if (ARM / name).exists():
            originals.append(archive(ARM / name, "arm/" + name))
    figures(receipt["cases"])
    files = [
        p
        for p in HERE.rglob("*")
        if p.is_file() and p.name != "index.json" and "__pycache__" not in p.parts
    ] + list(FIGURES.glob("*.png"))
    index = dict(
        scope=receipt["scope"],
        arm_provider_passed=arm_passed,
        originals=originals,
        files=[
            dict(path=str(p.relative_to(REPO)), sha256=sha(p.read_bytes()), bytes=p.stat().st_size)
            for p in sorted(files)
        ],
    )
    (HERE / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    print(json.dumps(dict(cases=42, files=len(files), arm_provider_passed=arm_passed)))


def figures(rows):
    FIGURES.mkdir(parents=True, exist_ok=True)
    for profile, filename, title in (
        (
            "resampled_jitter",
            "variable-cost-comparison.png",
            "Variable worker cost and owner jitter",
        ),
        ("median", "constant-cost-tradeoff.png", "Constant median worker cost: the trade-off"),
    ):
        chosen = [r for r in rows if r["rate"] == 5000000 and r["profile"] == profile]
        groups = list(dict.fromkeys((r["shape"], r["cost_session"]) for r in chosen))
        x = np.arange(len(groups))
        fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, constrained_layout=True)
        for age, shift, color in ((120, -0.18, "#929ca6"), (240, 0.18, "#217b91")):
            selected = [
                next(
                    r
                    for r in chosen
                    if (r["shape"], r["cost_session"]) == group
                    and r["maximum_pending_age_ms"] == age
                )
                for group in groups
            ]
            for ax, key, divisor in (
                (axes[0], "screening_percent", 1),
                (axes[1], "worst_source_gap_ms", 1000),
            ):
                ax.bar(
                    x + shift,
                    [r[key] / divisor for r in selected],
                    width=0.34,
                    color=color,
                    label=f"{age} ms pending limit",
                )
        axes[0].set(ylabel="Detector checks / dwells (%)", ylim=(0, 105))
        axes[0].legend(loc="upper right")
        axes[1].set(
            ylabel="Worst target check gap (s)",
            ylim=(0, 8),
            xticks=x,
            xticklabels=[
                ("Fixed" if g[0] == "original" else "Uneven") + "\n" + g[1][9:15] for g in groups
            ],
        )
        for ax in axes:
            ax.grid(axis="y", alpha=0.2)
            ax.set_axisbelow(True)
        fig.suptitle(f"5 MS/s, paired 300-second SDK replays\n{title}", fontsize=15)
        fig.supxlabel(
            "Synthetic IQ / controlled timing; uneven schedule rescaled from 2.5 MS/s. "
            "Not capture duty.",
            fontsize=9,
        )
        fig.savefig(FIGURES / filename, dpi=160, bbox_inches="tight")
        plt.close(fig)


if __name__ == "__main__":
    main()
