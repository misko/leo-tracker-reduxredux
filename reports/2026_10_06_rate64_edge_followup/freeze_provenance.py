"""Freeze report and pinned-source hashes without touching scientific artifacts."""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parent
    source = Path("/opt/leo-adaptive-memory/9181d637d/src")
    names = (
        "leo/analysis/starlink/templates.py",
        "leo/analysis/starlink/pilot_methods.py",
        "leo/analysis/starlink/acquisition.py",
        "leo/analysis/starlink/pilot_search_geometry.py",
        "leo/contracts/starlink_frequency.py",
        "leo/analysis/persistent_hop_trajectory.py",
        "leo/application/scanner_tracking.py",
        "leo/application/scanner_trajectory.py",
        "leo/application/persistent_hop_trajectory.py",
        "leo/storage/scanner_tracking_source.py",
        "leo/sky/doppler.py",
    )
    old = root.parent / "2026_10_06_rate64_edge_review"
    provenance = {
        "report_base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "scientific_source_root": str(source),
        "python": platform.python_version(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "matplotlib", "pytest")
        },
        "source_sha256": {
            name: digest(source / name) for name in names if (source / name).exists()
        },
        "original_report_sha256": {
            str(p.relative_to(old)): digest(p) for p in sorted(old.rglob("*")) if p.is_file()
        },
        "experiment_spec_sha256": digest(root / "data" / "experiment-spec.json"),
        "publication_scope": (
            "Report-only scripts, tests, JSON and scientific figures; "
            "no production or persisted contract edits."
        ),
    }
    (root / "data" / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    entries = [
        p
        for p in sorted(root.rglob("*"))
        if p.is_file()
        and p.name != "SHA256SUMS"
        and not any(part in ("__pycache__", ".pytest_cache", ".ruff_cache") for part in p.parts)
        and p.suffix not in (".log", ".pyc")
    ]
    (root / "SHA256SUMS").write_text(
        "".join(f"{digest(p)}  {p.relative_to(root)}\n" for p in entries)
    )
    print(
        f"Frozen {len(entries)} report artifacts and "
        f"{len(provenance['source_sha256'])} scientific modules."
    )


if __name__ == "__main__":
    main()
