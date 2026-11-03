#!/usr/bin/env python3
"""Build hashable receiver-authority mixtures from retained DS9 TSVs."""

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
REPORT = ROOT / "reports/2026_09_30_native_adaptive_deployment"
HERE = Path(__file__).resolve().parent

INPUTS = {
    "reference": {
        "candidates": REPORT / "tracking/candidates.tsv",
        "graph": REPORT / "tracking/graph-candidates.tsv",
    },
    "native": {
        "candidates": REPORT / "ds9/complete-scan-e1/candidates.tsv",
        "graph": REPORT / "ds9/complete-scan-e1/graph-candidates.tsv",
    },
}

VARIANTS = {
    "native-baseline": {"0": "native", "1": "native"},
    "rx0-reference": {"0": "reference", "1": "native"},
    "rx1-reference-control": {"0": "native", "1": "reference"},
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_candidates(path):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        return reader.fieldnames, list(reader)


def load_graph(path):
    lines = path.read_text().splitlines()
    if len(lines) < 2 or not lines[0].startswith("META\t"):
        raise ValueError(f"missing graph metadata: {path}")
    header = lines[1]
    rows = {}
    for line in lines[2:]:
        candidate_id = line.split("\t", 1)[0]
        if candidate_id in rows:
            raise ValueError(f"duplicate graph candidate: {candidate_id}")
        rows[candidate_id] = line
    return lines[0], header, rows


def main():
    HERE.mkdir(parents=True, exist_ok=True)
    candidates = {}
    graphs = {}
    header = None
    meta = None
    graph_header = None
    for name, paths in INPUTS.items():
        current_header, rows = load_candidates(paths["candidates"])
        current_meta, current_graph_header, graph_rows = load_graph(paths["graph"])
        if header is None:
            header = current_header
            meta = current_meta
            graph_header = current_graph_header
        if current_header != header or current_meta != meta or current_graph_header != graph_header:
            raise ValueError("reference/native TSV contracts differ")
        candidates[name] = rows
        graphs[name] = graph_rows

    manifest = {"schema": "org.leo.receiver-authority-ablation-inputs/v1", "inputs": {}}
    for name, paths in INPUTS.items():
        manifest["inputs"][name] = {
            kind: {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}
            for kind, path in paths.items()
        }

    manifest["variants"] = {}
    for variant, authority in VARIANTS.items():
        selected = []
        selected_graph = {}
        for receiver in ("0", "1"):
            source = authority[receiver]
            for row in candidates[source]:
                if row["receiver_id"] != receiver:
                    continue
                candidate_id = row["candidate_id"]
                if candidate_id not in graphs[source]:
                    raise ValueError(f"graph row missing: {source} {candidate_id}")
                if candidate_id in selected_graph:
                    raise ValueError(f"candidate ID collision: {candidate_id}")
                selected.append(row)
                selected_graph[candidate_id] = graphs[source][candidate_id]

        # Preserve each source's existing order within a receiver. The tracker
        # performs its own deterministic lane ordering.
        candidate_path = HERE / f"{variant}.candidates.tsv"
        graph_path = HERE / f"{variant}.graph-candidates.tsv"
        with candidate_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, delimiter="\t", fieldnames=header, lineterminator="\n")
            writer.writeheader()
            writer.writerows(selected)
        graph_path.write_text(
            "\n".join([meta, graph_header, *(selected_graph[row["candidate_id"]] for row in selected)])
            + "\n"
        )

        source_groups = {row["source_group_id"] for row in selected}
        manifest["variants"][variant] = {
            "authority_by_receiver": authority,
            "candidates": len(selected),
            "source_groups": len(source_groups),
            "receiver_candidates": {
                receiver: sum(row["receiver_id"] == receiver for row in selected)
                for receiver in ("0", "1")
            },
            "candidate_path": str(candidate_path.relative_to(ROOT)),
            "candidate_sha256": digest(candidate_path),
            "graph_path": str(graph_path.relative_to(ROOT)),
            "graph_sha256": digest(graph_path),
        }

    (HERE / "input-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
