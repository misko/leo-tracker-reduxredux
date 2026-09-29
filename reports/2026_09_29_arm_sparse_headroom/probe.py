"""Bounded same-input detector experiment on the identified worst saved dwell."""

import argparse
import json
import shlex
from pathlib import Path

from execute import HERE, connection, digest, save
from summarize import distribution, science


def main(args):
    panel = json.loads((HERE / "execution-panel.json").read_text())
    identity = ("scan-fw-319730ab74ce43e7", 138)
    group, source = next(
        (g, c)
        for g in panel["groups"]
        for c in g["calls"]
        if (c["case"]["context"]["session_id"], c["case"]["context"]["visit_index"]) == identity
    )
    reference = [
        json.loads(line)
        for line in (HERE / "local/fullprep-uncached" / (group["id"] + ".jsonl"))
        .read_text()
        .splitlines()
    ]
    expected = science(reference[source["sequence"] + 1]["result"])
    root, case = panel["remote_root"], source["case"]
    output = HERE / "local" / args.label
    output.mkdir(parents=True, exist_ok=False)
    lines = [
        "\t".join(
            map(
                str,
                (
                    i,
                    2500000,
                    120,
                    120,
                    root + "/" + case["template_files"]["exact"],
                    root + "/" + case["template_files"]["control"],
                    root + "/" + case["raw_file"],
                ),
            )
        )
        for i in range(args.repeats)
    ]
    manifest = output / "probe.tsv"
    manifest.write_text("\n".join(lines) + "\n")
    remote, upload = connection(args)
    executable = root + "/probe-" + digest(args.binary)[:16]
    upload(args.binary, executable)
    upload(manifest, root + "/probe.tsv")
    remote("chmod +x " + shlex.quote(executable))
    command = [
        executable,
        "--manifest",
        root + "/probe.tsv",
        "--thermal-path",
        "/sys/bus/iio/devices/iio:device1/in_temp0_raw",
        "--thermal-offset",
        "-2219",
        "--thermal-scale",
        "123.040771484",
    ]
    text = remote(shlex.join(command), timeout=120)
    (output / "probe.jsonl").write_text(text)
    records = [json.loads(line) for line in text.splitlines()]
    calls = [r["result"] for r in records[1:-1]]
    assert len(calls) == args.repeats
    exact = all(science(r) == expected for r in calls)
    result = {
        "identity": identity,
        "selection": "post-hoc worst control dwell; not representative panel",
        "binary_sha256": digest(args.binary),
        "receipt_sha256": digest(args.receipt),
        "output_sha256": digest(output / "probe.jsonl"),
        "exact_science": exact,
        "cpu_ms": distribution([r["call_cpu_ms"] for r in calls]),
        "wall_ms": distribution([r["call_wall_ms"] for r in calls]),
        "conditioned_ms": distribution(
            [sum(row["timings_ms"]["conditioned"] for row in r["rows"]) for r in calls]
        ),
    }
    save(output / "manifest.json", result)
    print(json.dumps(result), flush=True)
    assert exact


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--target", default="root@192.168.1.15")
    main(parser.parse_args())
