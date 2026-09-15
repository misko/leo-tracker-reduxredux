"""Package an already qualified detector without rebuilding or changing its seal."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from leo.radio.host_decision_release import load_host_decision_release


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(qualification: Path, output: Path) -> str:
    source = Path(__file__).resolve().parents[1]
    seal = json.loads((qualification / "sealed.json").read_text())
    build = json.loads((qualification / "decision.so.build.json").read_text())
    if seal["schema"] != "leo-host-adaptive-decision-qualification-v1":
        raise ValueError("unsupported qualification seal")
    if (
        digest(qualification / "decision.so") != seal["library_sha256"]
        or build["binary_sha256"] != seal["library_sha256"]
    ):
        raise ValueError("qualified detector binary has changed")
    sources = {}
    for recorded, expected in seal["sources_sha256"].items():
        original = Path(recorded)
        # The historical seal contains absolute paths. Translate its repository
        # relative suffix; never change the sealed document to make it portable.
        parts = original.parts
        repository_names = (source.name, "leo-tracker-single-rx-10m")
        root_index = next(parts.index(name) for name in repository_names if name in parts)
        relative = Path(*parts[root_index + 1 :])
        current = source / relative
        if digest(current) != expected:
            raise ValueError(f"qualified detector source has changed: {relative}")
        if relative.is_relative_to("src/leo"):
            sources[str(relative.relative_to("src/leo"))] = "sha256:" + expected
    # Additional release provenance closes the original seal's template gap.
    # This records the current tensor; it does not retroactively qualify it.
    sources["analysis/starlink/templates.py"] = "sha256:" + digest(
        source / "src/leo/analysis/starlink/templates.py"
    )
    templates = np.ascontiguousarray(
        [
            qin_edge_pilot_frame(2_500_000, edge, symbol_roll=roll)
            for edge in ("lower", "upper")
            for roll in (0, 17)
        ],
        dtype="<c16",
    )
    output.mkdir(parents=True, exist_ok=False)
    for filename, origin in {
        "decision.so": "decision.so",
        "build.json": "decision.so.build.json",
        "qualification-seal.json": "sealed.json",
    }.items():
        shutil.copyfile(qualification / origin, output / filename)
    manifest = output / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "leo-host-decision-release-v1",
                "files": {
                    name: "sha256:" + digest(output / name)
                    for name in ("decision.so", "build.json", "qualification-seal.json")
                },
                "sources": sources,
                "templates_sha256": "sha256:" + hashlib.sha256(templates.tobytes()).hexdigest(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    identity = "sha256:" + digest(manifest)
    load_host_decision_release(manifest, identity)
    return identity


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(package(args.qualification, args.output))
