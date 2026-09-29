"""Fresh compiler training on the first 32 randomized whole-dwell contexts."""

import argparse
import json
import shlex
import subprocess
from pathlib import Path

from execute import HERE, connection, digest, save


def main(args):
    panel = json.loads((HERE / "panel.json").read_text())
    execution = json.loads((HERE / "execution-panel.json").read_text())
    cases = {}
    for group in execution["groups"]:
        for call in group["calls"]:
            c = call["case"]["context"]
            cases[(c["session_id"], c["visit_index"])] = call["case"]
    selected = [
        cases[(c["context"]["session_id"], c["context"]["visit_index"])]
        for c in panel["selected"][:32]
    ]
    selection = "first 32 whole contexts of the seed-2026092901 shuffled primary panel"
    if args.include_tail:
        tail = cases[("scan-fw-319730ab74ce43e7", 138)]
        assert tail not in selected
        selected.append(tail)
        selection += "; plus measured clipped-grid tail scan-fw-319730ab74ce43e7/138"
    root = execution["remote_root"]
    profile = args.profile_dir
    output = HERE / "local" / args.label
    output.mkdir(parents=True, exist_ok=True)
    save(
        args.training_panel,
        {
            "selection": selection,
            "primary_panel_sha256": digest(HERE / "panel.json"),
            "training": selected,
            "held_out_count": 152 - len(selected),
            "compiler_training_only": True,
            "cli_calls_per_context": 1,
            "persistent_calls_per_context": 4,
        },
    )
    remote, upload = connection(args)
    remote("test ! -e " + shlex.quote(profile) + " && mkdir -p " + shlex.quote(profile))
    cli = root + "/pgo-train-cli"
    bench = root + "/pgo-train-bench"
    upload(args.build / "leo-native-glrt", cli)
    upload(args.build / "leo-native-glrt-bench", bench)
    remote("chmod +x " + shlex.quote(cli) + " " + shlex.quote(bench))

    def arguments(case):
        return [
            "--rate-hz",
            "2500000",
            "--dwell-ms",
            "120",
            "--probe-stride-ms",
            "120",
            "--exact-template",
            root + "/" + case["template_files"]["exact"],
            "--control-template",
            root + "/" + case["template_files"]["control"],
            "--input-ci16",
            root + "/" + case["raw_file"],
        ]

    for index, case in enumerate(selected):
        result = remote(shlex.join([cli, *arguments(case)]))
        save(output / f"cli-{index:02d}.json", json.loads(result))
    for edge in ("lower", "upper"):
        group = [c for c in selected if c["context"]["target"]["edge"] == edge]
        rows = []
        for _ in range(4):
            for c in group:
                rows.append(
                    "\t".join(
                        map(
                            str,
                            (
                                len(rows),
                                2500000,
                                120,
                                120,
                                root + "/" + c["template_files"]["exact"],
                                root + "/" + c["template_files"]["control"],
                                root + "/" + c["raw_file"],
                            ),
                        )
                    )
                )
        local = output / (edge + ".tsv")
        local.write_text("\n".join(rows) + "\n")
        upload(local, root + "/train-" + edge + ".tsv")
        result = remote(
            shlex.join(
                [
                    bench,
                    "--manifest",
                    root + "/train-" + edge + ".tsv",
                    "--thermal-path",
                    "/sys/bus/iio/devices/iio:device1/in_temp0_raw",
                    "--thermal-offset",
                    "-2219",
                    "--thermal-scale",
                    "123.040771484",
                ]
            )
        )
        (output / (edge + ".jsonl")).write_text(result)
        print("trained", edge, len(rows), "persistent calls", flush=True)
    collect(args, remote, output, profile)


def collect(args, remote, output, profile):
    remote("tar -C /tmp -cf " + profile + ".tar " + Path(profile).name)
    prefix = ["sudo", "-n", "sshpass", "-f", str(args.password_file)]
    subprocess.run(
        [
            *prefix,
            "scp",
            "-O",
            "-o",
            "LogLevel=ERROR",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            args.target + ":" + profile + ".tar",
            str(output / "profiles.tar"),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    subprocess.run(["sudo", "-n", "chmod", "644", str(output / "profiles.tar")], check=True)
    assert remote("sha256sum " + profile + ".tar").split()[0] == digest(output / "profiles.tar")
    save(
        output / "manifest.json",
        {
            "training_panel_sha256": digest(args.training_panel),
            "build_receipt_sha256": digest(args.build / "build-receipt.json"),
            "files": {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()},
        },
    )
    print("fresh profiles collected", digest(output / "profiles.tar"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--target", default="root@192.168.1.15")
    parser.add_argument("--profile-dir", default="/tmp/leo-native-glrt-headroom-pgo-profile-v1")
    parser.add_argument("--label", default="pgo-training")
    parser.add_argument("--training-panel", type=Path, default=HERE / "pgo-training-panel.json")
    parser.add_argument("--include-tail", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args()
    if args.collect_only:
        remote, _ = connection(args)
        collect(args, remote, HERE / "local" / args.label, args.profile_dir)
    else:
        main(args)
