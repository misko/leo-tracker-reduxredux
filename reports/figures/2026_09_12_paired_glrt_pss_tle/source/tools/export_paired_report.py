"""Publish the report and its linked evidence as a portable documentation bundle."""

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    destination = args.destination.resolve()
    figures = destination / "reports/figures/2026_09_12_paired_glrt_pss_tle"
    visited = {}

    def export(path):
        path = path.resolve()
        if path in visited:
            return visited[path]
        if path.is_relative_to(source / "reports") and path.suffix == ".md":
            target = destination / path.relative_to(source)
        elif path.is_relative_to(source):
            target = figures / "source" / path.relative_to(source)
        elif path.is_relative_to(Path("/srv/bulk/leo/experiments")):
            target = figures / path.relative_to(Path("/srv/bulk/leo/experiments"))
        else:
            raise ValueError(f"unrecognized report reference: {path}")
        if path.is_dir():
            target /= "README.md"
        elif path.suffix in (".json", ".csv") and path.stat().st_size > 5_000_000:
            target = target.with_suffix(target.suffix + ".gz")
        visited[path] = target
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            target.write_text(
                f"Historical experiment source: `{path}`.\n\n"
                "Linked figures and tables are included in this report bundle. "
                "The complete local experiment is retained at the source path.\n"
            )
        elif path.suffix == ".md":

            def link(match):
                linked = export(Path(match.group(1)))
                return "](" + os.path.relpath(linked, target.parent) + ")"

            text = re.sub(r"\]\((/[^)]+)\)", link, path.read_text())
            target.write_text(text)
        elif target.suffix == ".gz":
            target.write_bytes(gzip.compress(path.read_bytes(), mtime=0))
        elif path.suffix == ".csv":
            target.write_text(path.read_text())
        else:
            shutil.copyfile(path, target)
        return target

    export(source / "reports/2026_09_12_three_lane_glrt_pss_tle_comparison.md")
    snapshots = Path("/srv/bulk/leo/experiments/paired-five-glrt-pss-tle-20260912-v4/source")
    for path in snapshots.rglob("*"):
        if path.is_file():
            export(path)
    manifest = [
        dict(
            source=str(path),
            published=str(target.relative_to(destination)),
            sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        )
        for path, target in sorted(visited.items())
    ]
    (figures / "publication-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for path in destination.glob("reports/2026_09_12_*pss*.md"):
        for link in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if not link.startswith("https://"):
                assert (path.parent / link).exists(), (path, link)
    print(f"Exported {len(manifest)} report/evidence files with portable links")


if __name__ == "__main__":
    main()
