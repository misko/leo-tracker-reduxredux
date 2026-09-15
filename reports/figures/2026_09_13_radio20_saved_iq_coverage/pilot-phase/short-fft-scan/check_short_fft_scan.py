"""Check smaller proposal-ranking FFTs against direct NumPy spectra."""

import json, subprocess, hashlib
from pathlib import Path
import numpy as np

BASE = Path(__file__).parent
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
prior = json.loads((BASE / "heap-scan-build-v1.json").read_text())
sources = [
    Path(p)
    for p in prior["sources"]
    if p.endswith(".c") and not p.endswith("glrt_cpu_tracking_bench.c")
]
sources[0] = BASE / "short_fft_scan_bench.c"
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
            str(BASE / f"short-fft-scan-{arch}-v1"),
        ],
        check=True,
    )
out = BASE / "short-fft-scan-host-v1-results"
out.mkdir(exist_ok=False)
ranking = json.loads((BASE / "expanded-proposal-ranking-v1.json").read_text())
refs = np.fromfile(BASE / "direct-references.ci16", dtype="<i2").reshape(4, 3300, 4).astype(float)
ref = refs[0, :, 0] + 1j * refs[0, :, 1]
energy = np.vdot(ref, ref).real
result = dict(
    new_rf_samples=0,
    acceptance_gates_changed=False,
    live_tracking_qualified=False,
    source_sha256={str(p): digest(p) for p in sources},
    runner_sha256=digest(Path(__file__)),
    cases=[],
)
for case in ranking["cases"]:
    label = f"{case['label']}-{case['number']}"
    path = BASE / "combined-pilot-controls-v1" / label / "iq.ci16"
    raw = np.fromfile(path, dtype="<i2").reshape(-1, 2).astype(float)
    iq = raw[:, 0] + 1j * raw[:, 1]
    for size in (4096, 8192, 16384):
        completed = subprocess.run(
            [
                str(BASE / "short-fft-scan-host-v1"),
                str(BASE / "coarse-bank.ci16"),
                str(path),
                str(BASE / "direct-references.ci16"),
                "64",
                str(size),
            ],
            capture_output=True,
            check=True,
            timeout=15,
        )
        assert not completed.stderr
        rows = [json.loads(line) for line in completed.stdout.splitlines()]
        assert len(rows) == 65
        for row, expected in zip(rows[:-1], case["scores"][:64]):
            assert (row["epoch"], row["frequency"], row["score"]) == (
                expected["epoch"],
                expected["frequency"],
                expected["coarse_score"],
            )
            z = iq[row["epoch"] + 22 : row["epoch"] + 3322]
            score = float(
                max(abs(np.fft.fft(z * ref.conj(), size)) ** 2) / (energy * np.vdot(z, z).real)
            )
            np.testing.assert_allclose(row["rank_power"], score, rtol=2e-12, atol=2e-14)
        winner = int(np.argmax([r["rank_power"] for r in rows[:-1]])) + 1
        assert winner == rows[-1]["winner"]
        if size == 16384:
            assert winner == next(b for b in case["budgets"] if b["budget"] == 64)["single_winner"]
        journal = out / f"{label}-fft{size}.jsonl"
        journal.write_bytes(completed.stdout)
        peak = rows[winner - 1]
        worker = subprocess.run(
            [
                str(BASE / "expanded-worker-v1/bench"),
                str(path),
                str(BASE / "direct-references.ci16"),
                str(peak["epoch"]),
                str(peak["frequency"]),
                str(peak["score"]),
            ],
            capture_output=True,
            check=True,
            timeout=12,
        )
        assert not worker.stderr
        worker_path = out / f"{label}-fft{size}-worker.jsonl"
        worker_path.write_bytes(worker.stdout)
        wr = [json.loads(line) for line in worker.stdout.splitlines()]
        result["cases"].append(
            dict(
                label=case["label"],
                number=case["number"],
                fft=size,
                winner=winner,
                peak=peak,
                timing=rows[-1],
                terminal=wr[-1],
                accepted=sum(r["accepted"] for r in wr if r["kind"] == 3),
                journal_sha256=digest(journal),
                worker_journal_sha256=digest(worker_path),
                input_sha256=digest(path),
            )
        )
    print(label, [(c["fft"], c["winner"], c["accepted"]) for c in result["cases"][-3:]], flush=True)
result["payloads"] = {
    k: digest(BASE / v)
    for k, v in dict(
        probe="short-fft-scan-arm-v1",
        bank="coarse-bank.ci16",
        refs="direct-references.ci16",
        iq="combined-pilot-controls-v1/positive-12/iq.ci16",
    ).items()
}
result["worker_binary_sha256"] = digest(BASE / "expanded-worker-v1/bench")
with (out / "result.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
