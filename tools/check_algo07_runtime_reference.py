"""Replay the frozen guarded policy; this does not rerun numerical inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from algo07_science.policy import select
from algo07_science.uniqueness import from_additional_checks

from leo.cli.algo07_profile import digest, verify, write_new


def check(manifest: Path, audit_path: Path) -> dict:
    integrity = verify(manifest)
    if not integrity["verified"]:
        raise ValueError("Frozen runtime reference changed")
    frozen = json.loads(manifest.read_text())
    hashes = {r["path"]: r["sha256"] for r in frozen["files"]}

    def read_bound(path):
        path = Path(path).resolve()
        if hashes.get(str(path)) != digest(path):
            raise ValueError(f"Unbound reference input: {path}")
        return json.loads(path.read_text())

    audit = read_bound(audit_path)
    sources = [Path(p) for p in audit["source_sha256"]]
    receipts = {p.stem: p for p in sources if p.parent.name == "receipts"}
    checks = {p.parent.name: p for p in sources if p.name == "additional_checks.json"}
    failures = []
    selected = []
    for expected in audit["outcomes"]:
        case = expected["case"]
        receipt = read_bound(receipts[case])
        guards = {}
        for record in receipt["records"]["combined"]:
            if record.get("accepted"):
                guards[record["name"]] = from_additional_checks(read_bound(checks[case]))
        actual = select(receipt["baseline"], receipt["records"]["combined"], guards)
        for key in ("policy", "selected", "final", "review"):
            if actual[key] != expected[key]:
                failures.append(dict(case=case, field=key))
        if actual["selected"] is not None:
            selected.append(dict(case=case, selected=actual["selected"]))
    after = verify(manifest)
    return dict(
        passed=not failures and after["verified"],
        scope="exact saved-policy replay, not fresh numerical inference",
        cases=len(audit["outcomes"]),
        paired_arms=2 * len(audit["outcomes"]),
        failures=failures,
        selected=selected,
        reference_after=after,
        manifest_sha256=digest(manifest),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.manifest, args.audit)
    write_new(args.output, result)
    print(json.dumps(result))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
