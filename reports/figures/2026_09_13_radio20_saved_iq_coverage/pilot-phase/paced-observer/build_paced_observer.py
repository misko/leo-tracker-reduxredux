import json
import subprocess
from check_adjacent_c_validity import BASE as b, FW as fw, digest as h

names = [
    "glrt_tracking_observer.c",
    "glrt_tracking_iq_owner.c",
    "glrt_tracking_recent_iq.c",
    "glrt_tracking_iq.c",
    "glrt_native_trend.c",
    "glrt_native_schedule.c",
    "glrt_tracking_schedule.c",
    "glrt_native_solver.c",
]
src = [b / "paced_observer_bench.c"] + [fw / "tools" / x for x in names]
for arch, cc, flags in [
    ("host", "cc", []),
    (
        "arm",
        "/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc",
        ["-mcpu=cortex-a9", "-mfpu=neon"],
    ),
]:
    subprocess.run(
        [
            cc,
            "-std=c99",
            "-O3",
            "-pthread",
            "-Wall",
            "-Wextra",
            "-Werror",
            *flags,
            "-I",
            str(fw / "tools"),
            *map(str, src),
            "-lm",
            "-o",
            str(b / f"paced-observer-{arch}-v1"),
        ],
        check=True,
    )
out = b / "paced-observer-host-v1-results"
out.mkdir(exist_ok=False)
summaries = []
iq = (b / "paced-original-seed-input-v1/positive.ci16").read_bytes()
for offset in range(3):
    path = out / f"o{offset}.jsonl"
    retention = out / f"o{offset}.ci16"
    with path.open("x") as f:
        subprocess.run(
            [
                str(b / "paced-observer-host-v1"),
                str(b / "paced-original-seed-input-v1/positive.ci16"),
                str(b / "direct-references.ci16"),
                str(b / "adjacent-training-v1.txt"),
                str(offset),
                str(retention),
            ],
            stdout=f,
            check=True,
        )
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    summary = rows.pop()
    prior = [
        json.loads(x)
        for x in (b / "observer-cadence-host-v1-results" / f"o{offset}.jsonl")
        .read_text()
        .splitlines()
    ][:200]
    assert rows == prior and len(rows) == 200
    assert retention.read_bytes() == b"".join(
        iq[r["start"] * 4 : (r["start"] + 3300) * 4] for r in rows
    )
    assert summary["waits"] > 0
    summaries.append(summary)
    print(summary, flush=True)
with (b / "paced-observer-build-v1.json").open("x") as f:
    json.dump(
        dict(
            sources={str(p): h(p) for p in src + [b / "adjacent_arm_bench.c"]},
            payloads={
                n: h(b / p)
                for n, p in [
                    ("probe", "paced-observer-arm-v1"),
                    ("training", "adjacent-training-v1.txt"),
                    ("refs", "direct-references.ci16"),
                    ("iq", "paced-original-seed-input-v1/positive.ci16"),
                ]
            },
            host_rows_verified=600,
            host_summaries=summaries,
        ),
        f,
        indent=2,
    )
    f.write("\n")
