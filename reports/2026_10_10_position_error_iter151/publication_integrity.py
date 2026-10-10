"""Post-seal artifact inventory; no inference, reference port or receipt mutation."""

import argparse
import hashlib
import json
from pathlib import Path

from leo.contracts.digests import canonical_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PHASES = ("search", "native", "zero")
TERMINAL = {"complete", "failed", "incomplete", "budget-exhausted", "not-run-search-failed"}


def build(protocol, raw, publication, sources):
    """Return an explicit failed inventory when any required artifact is absent/invalid."""
    protocol, raw, publication = map(Path, (protocol, raw, publication))
    artifacts, failures = {}, []

    def read(path, *, structured=False):
        path = Path(path)
        try:
            data = path.read_bytes()
            artifacts[str(path)] = dict(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
            return json.loads(data) if structured else data
        except (OSError, ValueError) as error:
            failures.append(dict(path=str(path), reason=str(error)))
            return None

    def require(condition, path, reason):
        if not condition:
            failures.append(dict(path=str(path), reason=reason))

    plan = read(protocol, structured=True)
    if not isinstance(plan, dict):
        return dict(status="incomplete", failures=failures, artifact_sha256=artifacts)
    digest = canonical_digest(plan)
    members = plan.get("members", [])
    labels = [m.get("label") for m in members]
    require(len(labels) == 12 and len(set(labels)) == 12 and all(isinstance(x, str) for x in labels),
            protocol, "Expected twelve distinct member labels")
    valid_labels = [label for label in labels if isinstance(label, str)]
    phase_status = {}
    for label in valid_labels:
        for phase in PHASES:
            path = raw / label / phase / "result.json"
            row = read(path, structured=True)
            if not isinstance(row, dict):
                require(False, path, "Missing or invalid terminal receipt")
                continue
            valid = (row.get("protocol_sha256") == digest and row.get("label") == label
                     and row.get("status") in TERMINAL
                     and (phase == "search" or row.get("branch") == phase))
            require(valid, path, "Foreign identity or nonterminal phase")
            if valid:
                phase_status[(label, phase)] = row["status"]
        path = raw / label / "search" / "case.json"
        case = read(path, structured=True)
        require(isinstance(case, dict) and case.get("protocol_sha256") == digest
                and case.get("label") == label and isinstance(case.get("identity"), dict),
                path, "Missing or foreign reconstructed-case identity")
    batch_complete = 0
    for shard in (0, 1):
        for suffix in (".claim.json", ".json"):
            path = raw / f"batch-{shard}{suffix}"
            row = read(path, structured=True)
            valid = (isinstance(row, dict) and row.get("protocol_sha256") == digest
                     and row.get("shard") == shard)
            require(valid, path, "Missing or foreign batch identity")
            if not valid or suffix == ".claim.json":
                continue
            rows = row.get("members", [])
            expected = valid_labels[shard::2]
            complete = (isinstance(rows, list) and all(isinstance(r, dict) for r in rows)
                        and [r.get("label") for r in rows] == expected)
            if complete:
                complete = all("controller_failure" not in r and r.get("phases") == {
                    p: phase_status.get((r["label"], p)) for p in PHASES
                } and all(phase_status.get((r["label"], p)) in TERMINAL for p in PHASES)
                    for r in rows)
            require(complete, path, "Batch does not seal every assigned member/phase")
            batch_complete += int(complete)
    summary = read(publication / "SUMMARY.json", structured=True)
    require(isinstance(summary, dict) and summary.get("protocol_sha256") == digest
            and summary.get("all_terminal") is True
            and [r.get("label") for r in summary.get("rows", [])] == valid_labels,
            publication / "SUMMARY.json", "Summary identity/terminal membership mismatch")
    for name in ("RESULTS.md", "position_errors.png", "PUBLICATION_POLICY.md"):
        read(publication / name)
    for source in sources:
        read(source)
        source = Path(source)
        try:
            relative = str(source.relative_to(ROOT))
        except ValueError:
            relative = None
        expected = plan.get("source_sha256", {}).get(relative)
        if expected is not None:
            require(artifacts.get(str(source), {}).get("sha256") == expected, source,
                    "Frozen reporting source hash mismatch")
    # Bind and verify evaluation/report dependencies as recorded before execution.
    for name, expected in plan.get("evaluation_source_sha256", {}).items():
        path = ROOT / name
        read(path)
        require(artifacts.get(str(path), {}).get("sha256") == expected, path,
                "Frozen evaluation source hash mismatch")
    return dict(
        status="complete" if not failures else "incomplete",
        protocol_file_sha256=artifacts[str(protocol)]["sha256"],
        receipt_protocol_canonical_digest=digest,
        digest_semantics="Receipt protocol_sha256 is canonical_digest(parsed protocol), not file SHA256.",
        terminal_phase_count=len(phase_status), terminal_batch_count=batch_complete,
        failures=failures, artifact_sha256=artifacts,
        limitations="Raw scientific receipts remain local. Hashes bind retained evidence but do not "
        "provide standalone remote replay. This inventory does not recompute numerical results.",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    parser.add_argument("--raw", type=Path, default=HERE / "results")
    parser.add_argument("--publication", type=Path, default=HERE)
    args = parser.parse_args()
    sources = [HERE / name for name in ("report.py", "publish.py", "publication_integrity.py",
                                        "test_publication_integrity.py")]
    sources.append(HERE.parent / "2026_10_09_position_error_iter129/report_cohort.py")
    result = build(args.protocol, args.raw, args.publication, sources)
    with (args.publication / "PUBLICATION_INTEGRITY.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    if result["status"] != "complete":
        raise SystemExit("Incomplete publication evidence; inspect PUBLICATION_INTEGRITY.json")


if __name__ == "__main__":
    main()
