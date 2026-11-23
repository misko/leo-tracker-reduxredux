"""Score the prespecified graph replays and orbit regression from sealed stores."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_score import PHYSICAL, references
from aperture_trial import ARMS, read, write
from full_short_orbit_transfer import PAIR, PAIR_SHA
from joint_publication import artifacts
from leo.contracts.digests import canonical_digest
from leo.presentation.localization_v3 import owner_digest
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from mixture_score import section


DATA = Path(__file__).resolve().parent / "measurements"


def position(case):
    row, = [r for r in read(PHYSICAL)["cases"] if r["dataset_label"] == case and r["authority_eligible"]]
    return [row["reference"][k] for k in ("latitude_deg", "longitude_deg")]


def publication(root, pin, offer):
    report = read(root / "joint-research-receipt.json")
    receipt = report["receipt"]
    terminal = read(root / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
    evidence = artifacts(root, receipt)
    if (terminal["native_sha256"] != pin or report["saved_digest"] != pin
            or receipt["region"] != offer or terminal["region"] != offer
            or canonical_digest(terminal) != receipt["terminal_sha256"] or report["evidence"] != json.loads(json.dumps(evidence))):
        raise ValueError("A saved terminal, detector, supplied region or web publication differs")
    detail = FastStandardAnalysisStore(root).detail(receipt["run_id"])
    owners = {}
    if receipt["decision"] == "complete":
        for arm in ARMS:
            rows = {oid: satellite for oid, satellite, _ in report["selected_rows"][arm]}
            signed = detail["arms"][arm]
            if owner_digest(rows) != signed["owner_sha256"] or len(rows) != signed["associated_points"]:
                raise ValueError("Replayed owner rows differ from the published solution")
            owners[arm] = dict(count=len(rows), digest=signed["owner_sha256"])
    return dict(decision=receipt["decision"], terminal=terminal, owners=owners, route=report["route"],
                process_machine=report["machine"], solve=report["solve"], early_regional=report["early_regional"],
                publication_cpu_s=report["publication_cpu_s"], publication_elapsed_s=report["publication_elapsed_s"],
                receipt=receipt, evidence=evidence, source_sha256=report["source_sha256"])


def score_graph(root):
    raw = json.loads(gzip.decompress((DATA / "full-short-DS30-0016-raw.json.gz").read_bytes()))["runs"]["candidate"]
    south = read(DATA / "full-short-south.json")["cases"]
    result = {}
    for case in ("physical", "south-inside", "south-far"):
        if case == "physical":
            original, previous_arms = raw["publication"], raw["verified"]["arms"]
            pin = raw["detection"]["native_sha256"]
            truth = position("DS30-0016")
        else:
            original = south["far" if case == "south-far" else "containing"]
            previous_arms, pin = original["terminal"]["arms"], original["native_pin"]
            truth = references()["south-containing"]
        row = publication(Path(str(root) + "-" + case), pin, original["receipt"]["region"])
        row["control"] = dict(decision=original["receipt"]["decision"], score=section(previous_arms, truth, previous_arms),
                              solve=original["solve"], owners=original["owners"] if case != "physical" else
                              {a: len(v) for a,v in original["selected_rows"].items()})
        row["score"] = section(row["terminal"]["arms"], truth, previous_arms)
        result[case] = row
    return result


def score_orbit(root):
    request = read(root / "request.json")
    if request["pair_sha256"] != PAIR_SHA or sha256(PAIR.read_bytes()).hexdigest() != PAIR_SHA:
        raise ValueError("Orbit regression assignment changed")
    pair = read(PAIR)
    previous = pair["runs"]["baseline"]
    mode = "guard" if (root / "guard-process.json").exists() else "current"
    status = read(root / f"{mode}-process.json")
    if status["exit_code"]:
        raise ValueError("The saved regression did not exit successfully")
    row = publication(root / mode, request["binding"]["source_digest"], previous["receipt"]["region"])
    truth = position("DS30-0022")
    row.update(mode=mode, process=status, guard_entries=read(root / f"{mode}-support.json"), binding=request["binding"],
               archived_failure=pair["runs"]["candidate"]["receipt"]["decision"],
               v2=dict(score=section(previous["arms"], truth, previous["arms"]), owners=previous["owners"]),
               score=section(row["terminal"]["arms"], truth, previous["arms"]))
    return row


def score_projector(root):
    from full_short_run import GEOGRAPHIC_SHA
    from full_short_graph_transfer import SOUTH

    cases = read(DATA / "full-short-south.json")["cases"]
    results = {}
    for case in ("containing", "far"):
        base = cases[case]
        output = Path(str(root) + "-" + case)
        row = publication(output, base["native_pin"], base["receipt"]["region"])
        original = read(SOUTH / case / "joint-research-receipt.json")
        new = read(output / "joint-research-receipt.json")
        binding = read(output / "full-short-recipe.json")
        counts = row["solve"]["geographic_projector"]
        if (binding["geographic_sha256"] != GEOGRAPHIC_SHA or not counts["calls"] or counts.get("original_fallback")
                or new["selected_rows"] != original["selected_rows"] or row["terminal"] != base["terminal"]
                or new["evidence"]["images"] != original["evidence"]["images"]
                or new["evidence"].get("path") != original["evidence"].get("path")):
            raise ValueError("The fused projection did not preserve the standard terminal, owners, path or figures")
        if row["decision"] == "complete":
            grids = [FastStandardAnalysisStore(p).position_grid(row["receipt"]["run_id"]) for p in (output, SOUTH / case)]
            for grid in grids:
                del grid["elapsed_seconds"]
            if not grids[0]["complete"] or grids[0] != grids[1]:
                raise ValueError("Geographic projection changed at least one grid value")
        proof = dict(row["early_regional"][0]["result"])
        before = dict(base["proof"]["result"])
        changes = {}
        for group, old_receiver in before.pop("receivers", {}).items():
            receiver = proof["receivers"][group]
            delta = abs(old_receiver["gain"] - receiver["gain"])
            if delta > 1e-10 or any(receiver[k] != v for k, v in old_receiver.items() if k != "gain"):
                raise ValueError("Regional gain or winner changed")
            changes[group] = delta
        if changes and set(proof.pop("receivers")) != set(changes):
            raise ValueError("Regional receiver set changed")
        if proof != before:
            raise ValueError("The geographic verdict changed")
        row.update(control_solve=base["solve"], control_proof_cpu_s=base["proof"]["cpu_s"],
                   receiver_gain_abs_deltas=changes, geographic_sha256=GEOGRAPHIC_SHA)
        results[case] = row
    return results


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    operations = {"orbit": score_orbit, "graph": score_graph, "projector": score_projector}
    cli.add_argument("mode", choices=operations)
    cli.add_argument("root", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    write(args.output, operations[args.mode](args.root))
