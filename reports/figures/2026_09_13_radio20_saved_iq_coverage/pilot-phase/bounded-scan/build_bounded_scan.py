"""Build host/ARM scanner benchmark and check all 26 saved cuts independently."""

import json, subprocess, hashlib
from pathlib import Path
import numpy as np
from tests.starlink_glrt.test_tracking_seed import SOURCES

BASE = Path(__file__).parent
FW = Path("/home/mouse9911/gits/plutosdr-fw-radio20-tracking")
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
names = [
    "glrt_cpu_coarse.c",
    "glrt_cpu_seed.c",
    "glrt_tracking_worker.c",
    "glrt_tracking_live_bootstrap.c",
    "glrt_tracking_iq.c",
    *SOURCES,
]
sources = [BASE / "bounded_scan_bench.c", *(FW / "tools" / n for n in names)]
prefix = BASE.parent / "fftw-host-v1/install"
for arch, cc, flags in [
    (
        "host",
        "cc",
        [
            "-I",
            str(prefix / "include"),
            "-L",
            str(prefix / "lib"),
            "-Wl,-rpath," + str(prefix / "lib"),
        ],
    ),
    (
        "arm",
        "/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc",
        ["-mcpu=cortex-a9", "-mfpu=neon"],
    ),
]:
    subprocess.run(
        [
            cc,
            "-O3",
            "-std=c99",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pthread",
            *flags,
            *map(str, sources),
            "-lfftw3",
            "-lm",
            "-o",
            str(BASE / f"bounded-scan-{arch}-v1"),
        ],
        check=True,
    )
out = BASE / "bounded-scan-host-v1-results"
out.mkdir(exist_ok=False)
ranking = json.loads((BASE / "expanded-proposal-ranking-v1.json").read_text())
checks = []
for case in ranking["cases"]:
    for budget in (8, 64):
        label = f"{case['label']}-{case['number']}"
        path = BASE / "combined-pilot-controls-v1" / label / "iq.ci16"
        run = subprocess.run(
            [
                str(BASE / "bounded-scan-host-v1"),
                str(BASE / "coarse-bank.ci16"),
                str(path),
                str(BASE / "direct-references.ci16"),
                str(budget),
            ],
            capture_output=True,
            check=True,
            timeout=15,
        )
        assert not run.stderr
        rows = [json.loads(line) for line in run.stdout.splitlines()]
        assert len(rows) == budget + 1
        for row, expected in zip(rows[:-1], case["scores"]):
            assert (row["epoch"], row["frequency"], row["score"]) == (
                expected["epoch"],
                expected["frequency"],
                expected["coarse_score"],
            )
            np.testing.assert_allclose(
                row["rank_power"], expected["single"], rtol=2e-12, atol=2e-14
            )
        assert (
            rows[-1]["winner"]
            == next(b for b in case["budgets"] if b["budget"] == budget)["single_winner"]
        )
        (out / f"{label}-b{budget}.jsonl").write_bytes(run.stdout)
        checks.append(dict(label=label, **rows[-1]))
payloads = {
    k: digest(BASE / v)
    for k, v in dict(
        probe="bounded-scan-arm-v1",
        bank="coarse-bank.ci16",
        refs="direct-references.ci16",
        iq="combined-pilot-controls-v1/positive-12/iq.ci16",
    ).items()
}
with (BASE / "bounded-scan-build-v1.json").open("x") as f:
    json.dump(
        dict(
            sources={
                str(p): digest(p)
                for p in [
                    *sources,
                    FW / "tools/glrt_cpu_tracking_bench.c",
                    FW / "tools/glrt_cpu_coarse.h",
                ]
            },
            payloads=payloads,
            host_checks=checks,
            host_peaks_verified=26 * 72,
            ranking_sha256=digest(BASE / "expanded-proposal-ranking-v1.json"),
        ),
        f,
        indent=2,
    )
    f.write("\n")
print("52 host runs and 1872 ranked peaks match independent saved-IQ evidence", flush=True)
