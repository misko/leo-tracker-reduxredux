"""Identity-token-only exposure audit and frozen metadata whole-group assignment."""

import hashlib
import json
import math
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OTHER = Path("/home/mouse9911/gits/leo-tracker-reduxredux/reports")


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    plan = read(HERE / "protocol.json")
    manifest = read(HERE / "local/manifest.json")
    rows = manifest["captures"]
    parents = {
        "DS16": OTHER / "2026_10_08_ds17_post_ds16/local/parent-manifest.json",
        "DS17": OTHER / "2026_10_08_ds18_post_ds17/local/parent-manifest.json",
        "DS18": OTHER / "2026_10_08_ds18_post_ds17/local/manifest.json",
        "POST18-RESERVE": ROOT / "reports/2026_10_09_position_error_iter75/local/manifest.json",
    }
    disjoint = {}
    for name, path in parents.items():
        old = read(path)
        overlaps = {
            key: sorted({r[key] for r in rows} & {r[key] for r in old["captures"]})
            for key in ("session_id", "uncompressed_sha256")
        }
        assert not any(overlaps.values()), name
        disjoint[name] = dict(
            manifest_sha256=sha(path), members=len(old["captures"]), overlaps=overlaps
        )
    tokens = sorted(
        {
            str(r[k])
            for r in rows
            for k in ("session_id", "recording_manifest_sha256", "uncompressed_sha256")
        }
    )
    # Default ignored/local receipts are explicitly included. Output contains only
    # matching identity tokens, never the matching localization-value line.
    command = [
        "/home/mouse9911/.codex/packages/standalone/releases/0.161.0-x86_64-unknown-linux-musl/codex-path/rg",
        "--only-matching",
        "--with-filename",
        "--fixed-strings",
        "--hidden",
        "--no-ignore",
        "--glob",
        "*.json",
        "--glob",
        "*.md",
        "--glob",
        "*.py",
        "--glob",
        "*.csv",
        "--glob",
        "*.txt",
        "--glob",
        "!**/.git/**",
        "--glob",
        "!**/__pycache__/**",
        "--glob",
        "!**/2026_10_09_position_error_iter89/**",
    ]
    for token in tokens:
        command.extend(["-e", token])
    command.extend([str(ROOT / "reports"), str(OTHER)])
    result = subprocess.run(command, capture_output=True, text=True)
    (HERE / "exposure-search.json").write_text(
        json.dumps(
            dict(
                argv=command,
                exit_code=result.returncode,
                stderr=result.stderr,
                output_policy="Only identity tokens and filenames; "
                "no matching lines/localization values",
            ),
            indent=2,
        )
        + "\n"
    )
    assert result.returncode in (0, 1), result.stderr
    matches = {t: set() for t in tokens}
    for line in result.stdout.splitlines():
        path, token = line.split(":", 1)
        assert token in matches, line
        matches[token].add(path)
    exposure = []
    for row in rows:
        paths = sorted(
            set().union(
                *(
                    matches[str(row[k])]
                    for k in ("session_id", "recording_manifest_sha256", "uncompressed_sha256")
                )
            )
        )
        known = row["session_id"] in plan["known_consumed_sessions"]
        outcome_paths = [
            p
            for p in paths
            if "/live/" in p
            and any(p.endswith(suffix) for suffix in ("document.json", "browser.json"))
        ]
        classification = (
            "consumed_known_live_diagnostic"
            if known
            else (
                "consumed_prior_live_outcome_receipt"
                if outcome_paths
                else "prior_identity_match_requires_classification"
                if paths
                else "no_match_in_searched_roots_independence_unproven"
            )
        )
        exposure.append(
            dict(
                dataset_label=row["dataset_label"],
                session_id=row["session_id"],
                matching_files=paths,
                outcome_evidence_files=outcome_paths,
                exposure=classification,
                consumed=known or bool(outcome_paths),
            )
        )
    # Connected components join acquisition identities and conservative2h blocks.
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        parent[max(a, b)] = min(a, b)

    links, explicit_links = {}, []
    acquisition_keys = {
        "campaign_id",
        "capture_group_id",
        "acquisition_id",
        "parent_capture_id",
        "parent_session_id",
    }

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in acquisition_keys and isinstance(child, str) and child:
                    yield key, child
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    for i, row in enumerate(rows):
        identities = [
            ("utc2h_block", str(row["capture_start_utc_ns"] // (7200 * 10**9))),
            ("iq", row["uncompressed_sha256"]),
            ("manifest", row["recording_manifest_sha256"]),
        ]
        metadata = read(HERE / "local" / row["metadata_snapshot"])
        acquisition = sorted(set(walk(metadata)))
        identities.extend(acquisition)
        explicit_links.append(
            dict(session_id=row["session_id"], acquisition_identifiers=acquisition)
        )
        for identity in identities:
            if identity in links:
                union(i, links[identity])
            else:
                links[identity] = i
    groups = {}
    for i in range(len(rows)):
        groups.setdefault(find(i), []).append(i)
    assigned = []
    for indices in groups.values():
        identities = sorted(
            rows[i]["session_id"]
            + "|"
            + rows[i]["recording_manifest_sha256"]
            + "|"
            + rows[i]["uncompressed_sha256"]
            for i in indices
        )
        rank = hashlib.sha256(
            (plan["random_seed"] + "\n" + "\n".join(identities)).encode()
        ).hexdigest()
        consumed = any(exposure[i]["consumed"] for i in indices)
        unresolved = any(
            exposure[i]["exposure"] == "prior_identity_match_requires_classification"
            for i in indices
        )
        assigned.append(
            dict(
                group_id="group-" + rank[:16],
                random_rank=rank,
                member_labels=[rows[i]["dataset_label"] for i in indices],
                session_ids=[rows[i]["session_id"] for i in indices],
                consumed=consumed,
                unresolved_exposure=unresolved,
                assignment="development"
                if consumed
                else "pending_exposure_review"
                if unresolved
                else "unassigned",
            )
        )
    eligible = sorted(
        [g for g in assigned if g["assignment"] == "unassigned"], key=lambda g: g["random_rank"]
    )
    reserve_count = max(1, math.floor(0.2 * len(eligible))) if len(eligible) >= 5 else 0
    for i, group in enumerate(eligible):
        group["assignment"] = "closed_reserve" if i < reserve_count else "development"
    receipt = dict(
        dataset_id=manifest["dataset_id"],
        manifest_sha256=sha(HERE / "local/manifest.json"),
        protocol_sha256=sha(HERE / "protocol.json"),
        counts=manifest["counts"],
        window=manifest["capture_start_window_utc"],
        disjointness=disjoint,
        members=[dict(row, exposure=exposure[i]) for i, row in enumerate(rows)],
        exposure_search=dict(
            roots=[str(ROOT / "reports"), str(OTHER)],
            hidden_ignored_included=True,
            unavailable_locations=result.stderr,
            limitations="External machines/notebooks/conversations not audited; "
            "no match is not unseen proof; matches classified without opening outcomes.",
        ),
        grouping=dict(
            seed=plan["random_seed"],
            utc_block_seconds=7200,
            acquisition_fields=sorted(acquisition_keys),
            metadata_links=explicit_links,
            groups=sorted(assigned, key=lambda g: g["random_rank"]),
            group_assignment_counts=dict(Counter(g["assignment"] for g in assigned)),
            reserve_count=reserve_count,
            limitations="Fixed2h blocks and available acquisition IDs do not prove independence. "
            "Missing campaign metadata leaves longer clock/thermal dependence possible.",
        ),
        no_outcome_access=True,
        existing_reserve_outcomes_closed=True,
    )
    (HERE / "membership.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                members=len(rows),
                exposure_counts=dict(Counter(e["exposure"] for e in exposure)),
                groups=len(assigned),
                assignments=receipt["grouping"]["group_assignment_counts"],
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
