"""Metadata-only successor preparation; no catalogue or recording inventory."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARENT = ROOT / "reports/2026_10_09_position_error_iter89/local"
START = "2026-10-09T15:46:15+00:00"
END = "2026-10-10T03:33:34+00:00"
NAME = "POST18-LATER-20261010"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare():
    manifest = PARENT / "manifest.json"
    seal_path = PARENT / "seal.json"
    if sha(manifest) != "421421e1ff6c94e760960290fe94954c00776a05606e4e4433adc4f2cf02c633":
        raise ValueError("Published parent89 manifest changed")
    if sha(seal_path) != "28b6f216a8d63602ff15fd997b7b2582c5ffb125461915cd888a90ef837d3b0d":
        raise ValueError("Published parent89 seal changed")
    parent = json.loads(manifest.read_text())
    if (
        parent["dataset_id"] != "POST18-NEWER-20261009"
        or parent["capture_start_window_utc"][1] != START
    ):
        raise ValueError("Successor boundary differs from parent authority")
    for name, expected in json.loads(seal_path.read_text())["files"].items():
        if "sha256:" + sha(PARENT / name) != expected:
            raise ValueError("Sealed parent metadata changed: " + name)
    prior_path = PARENT.parent / "protocol.json"
    if sha(prior_path) != "0e93118d9449cc2571aadbb0148365663acbed1d1b15eff60ff7a17396c02de0":
        raise ValueError("Published parent89 protocol changed")
    prior = json.loads(prior_path.read_text())
    mint = Path(prior["mint_source"])
    runtime_roots = [Path(p) for p in prior["frozen_api_pythonpath"].split(":")]
    files = {
        mint,
        mint.parent / "test_mint.py",
        manifest,
        seal_path,
        prior_path,
        HERE / "prepare.py",
        HERE / "README.md",
        Path(prior["python_resolved"]),
    }
    disjoint_authorities = [
        ROOT / "reports/2026_10_08_ds16_last16h/manifest.json",
        Path("/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_08_ds17_post_ds16/local/manifest.json"),
        Path("/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_08_ds18_post_ds17/local/manifest.json"),
        ROOT / "reports/2026_10_09_position_error_iter75/local/manifest.json",
        manifest,
    ]
    files.update(disjoint_authorities)
    for root in runtime_roots:
        files.update(root.rglob("*.py"))
        files.update(root.rglob("*.so"))
    for path in files:
        if str(path) in prior["source_sha256"] and sha(path) != prior["source_sha256"][str(path)]:
            raise ValueError("Inherited mint/runtime source changed: " + str(path))
    arguments = [
        "--dataset-id",
        NAME,
        "--parent-dataset",
        parent["dataset_id"],
        "--parent",
        str(PARENT),
        "--start",
        START,
        "--end",
        END,
        "--output",
        str(HERE / "local"),
    ]
    command = [
        "sudo",
        "-n",
        "-u",
        "leo",
        "env",
        "PYTHONDONTWRITEBYTECODE=1",
        "PYTHONPATH=" + prior["frozen_api_pythonpath"],
        prior["python_executable"],
        str(mint),
    ]
    return dict(
        dataset_id=NAME,
        parent_dataset=parent["dataset_id"],
        start=START,
        end=END,
        cutoff_authority="clock returned 2026-10-10 03:33:34 UTC before new live inventory",
        parent_authority=str(PARENT),
        parent_manifest_sha256=sha(manifest),
        parent_seal_sha256=sha(seal_path),
        disjointness_authorities={str(path): sha(path) for path in disjoint_authorities},
        output=str(HERE / "local"),
        mint_command=command + ["mint"] + arguments,
        verify_command=command + ["verify"] + arguments,
        membership="All whole sealed adaptive recordings started in [start,end), sealed by end; "
        "published and unpublished; no analysis-readiness or quality gate",
        existing_reserves="POST18-RESERVE eleven and parent89 newer009–016 remain closed",
        split="None initially; whole cohort outcomes closed pending exposure audit "
        "and globally frozen candidate",
        exposure_policy="Exact session/input/IQ digest metadata matches and filenames only; "
        "known consumed development and live diagnostics remain consumed. Registry scope includes "
        "both worktree reports and existing75/89 exposure registries; access failures explicit. "
        "No match is not proof of unseen validation.",
        scope="No RF, retention hold, analysis, localization outcome access, or QNAP writes",
        source_sha256={str(path): sha(path) for path in sorted(files)},
    )


def main():
    plan = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
