"""Replay spaced strongest missed proposals through the actual C worker."""

import hashlib, json, subprocess
from pathlib import Path
import numpy as np
from tests.starlink_glrt.test_tracking_seed import SOURCES

BASE = Path(__file__).parent
FW = Path("/home/mouse9911/gits/plutosdr-fw-radio20-tracking")
PREFIX = Path("/srv/bulk/leo/glrt-deployment-20260909/fftw-host-v1/install")
out = BASE / "missed-candidate-replay-v1"
out.mkdir(exist_ok=False)
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
names = [
    "glrt_cpu_coarse.c",
    "glrt_cpu_seed.c",
    "glrt_tracking_worker.c",
    "glrt_tracking_live_bootstrap.c",
    "glrt_tracking_iq.c",
    *SOURCES,
]
command = [
    "cc",
    "-std=c99",
    "-O3",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-pthread",
    "-I",
    str(PREFIX / "include"),
    str(BASE / "missed_candidate_bench.c"),
    *(str(FW / "tools" / n) for n in names),
    "-L",
    str(PREFIX / "lib"),
    "-Wl,-rpath," + str(PREFIX / "lib"),
    "-lfftw3",
    "-lm",
    "-o",
    str(out / "bench"),
]
subprocess.run(command, check=True, capture_output=True)
coverage = json.loads((BASE / "saved-visit-dense-coverage-v1.json").read_text())
selected = []
for row in sorted(
    coverage["cases"]["60_CH3"]["measurements"], key=lambda r: -r["maximum_rank_power"]
):
    if row["offset"] + 447851 > coverage["cases"]["60_CH3"]["complex_samples"]:
        continue
    if all(abs(row["offset"] - r["offset"]) >= 500000 for r in selected):
        selected.append(row)
    if len(selected) == 10:
        break
cases = [
    (f"candidate-{i}", BASE / "two-frequency-visits60-v3/visit-0/iq.ci16", r, "60_CH3")
    for i, r in enumerate(selected)
]
for label in ("positive", "control"):
    row = max(coverage["cases"][label]["measurements"], key=lambda r: r["maximum_rank_power"])
    cases.append((label, BASE / f"paced-original-seed-input-v1/{label}.ci16", row, label))
result = dict(
    scope="saved_proposals_actual_C_resolve_and_past_support",
    rf_samples=0,
    receiver_time="frozen",
    native_tracking_qualified=False,
    compile_command=command,
    source_sha256={n: digest(FW / "tools" / n) for n in [*names, "glrt_cpu_tracking_bench.c"]},
    bench_source_sha256=digest(BASE / "missed_candidate_bench.c"),
    runner_sha256=digest(Path(__file__)),
    binary_sha256=digest(out / "bench"),
    coverage_sha256=digest(BASE / "saved-visit-dense-coverage-v1.json"),
    cases=[],
)
for label, path, proposal, key in cases:
    expected = coverage["cases"][key]["iq_sha256"]
    assert digest(path) == expected
    iq = np.memmap(path, mode="r", dtype="<i2").reshape(-1, 2)
    first = proposal["offset"]
    cut = iq[first : first + 447851]
    assert len(cut) == 447851
    directory = out / label
    directory.mkdir()
    cut.tofile(directory / "iq.ci16")
    run = subprocess.run(
        [
            str(out / "bench"),
            str(BASE / "coarse-bank.ci16"),
            str(directory / "iq.ci16"),
            str(BASE / "direct-references.ci16"),
        ],
        capture_output=True,
        timeout=12,
    )
    (directory / "stdout.jsonl").write_bytes(run.stdout)
    (directory / "stderr.txt").write_bytes(run.stderr)
    run.check_returncode()
    rows = [json.loads(line) for line in run.stdout.splitlines()]
    np.testing.assert_allclose(
        rows[0]["rank_power"], proposal["maximum_rank_power"], rtol=2e-12, atol=2e-14
    )
    past = [r for r in rows if r["kind"] == 3]
    terminal = rows[-1]
    assert terminal["kind"] == "terminal" and terminal["worker_result"] in (1, -6, -7)
    assert len(past) == terminal["retained_past"]
    result["cases"].append(
        dict(
            label=label,
            source_path=str(path),
            source_sha256=expected,
            source_offset=first,
            input_sha256=digest(directory / "iq.ci16"),
            journal_sha256=digest(directory / "stdout.jsonl"),
            proposal=rows[0],
            terminal=terminal,
            accepted=sum(r["accepted"] for r in past),
            max_past_coherence=max((r["coherence"] for r in past), default=0),
        )
    )
    print(json.dumps(result["cases"][-1]), flush=True)
with (out / "result.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
