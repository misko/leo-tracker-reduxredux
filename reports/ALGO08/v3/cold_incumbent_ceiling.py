"""Account for the saved cold work after the usual rank returns its first assignment."""

from gzip import decompress
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
THRESHOLD_NS = 500_000_000
WEAK = {
    "containing": (
        "22b656b94538a9534e87d93c33e0922c03783fd2c383c65c09c56aa1da66b17a",
        "98365718e60164134084810baf1890aa81a9dc9c2e1804bd77d2b1b4ca1c2d79",
    ),
    "translated": (
        "f399c830c51e554c83da309bc548c7530a2ed4223b3657061456e64aae38e623",
        "246568330488c0cc61ec7f0d5137ebd0fe0278983b2b8787dda4e774ea62fdfc",
    ),
}
MEDIUM = {
    "publication": "1b95d3d9b74875c277659fd7b8e0b6547abeeabbfc7071a068aebc31c30c5b6d",
    "rank": "ce0fcd3c0156e6a30bb8d28746bd5b8a49b8db8390573c63a554717b3d7473f6",
    "verification": "e8a4fad9eea4ee7381d4717f1f3c52423a9b643d0225207cf374b5f461a78196",
}
DENSE = {
    "publication": "dfbe0c40ae78187d583198ab97517c204708a5c7d899d0efe9f76f646a82205a",
    "verification": "da352d9b4b08a7d79be2fb46735afc7b63f2fee8bb29c1c886e268fae012dd1d",
    "rank_trace": "17e1a6addf19f6bb22e6d7941a7bdfc6ab9a88d2b8c1c8ae960b5c7983f0b2d2",
    "rank_binding": "65a61ecb90afaa25db668cb8e966de13feab1d6b5cd9eb3eeccf142bbc69c602",
}


def checked(path, digest):
    raw = path.read_bytes()
    data = decompress(raw) if path.suffix == ".gz" else raw
    # Some established archive pins bind the compressed bytes and others bind the JSON.
    if digest not in (sha256(raw).hexdigest(), sha256(data).hexdigest()):
        raise ValueError(f"Receipt SHA-256 mismatch for {path}")
    return json.loads(data)


def without_clocks(trace):
    return trace | {key: [{k: v for k, v in row.items() if k != "cpu_ns"} for row in trace[key]]
                    for key in ("prefix", "completed")}


def account(cold_ns, trace, rank_ns=None):
    decisions = trace["scores"]
    count = len(decisions)
    prefixes, completed = trace["prefix"], trace["completed"]
    for rows in (prefixes, completed):
        branches = [row["branch"] for row in rows]
        if (len(set(branches)) != len(branches) or not set(branches) <= set(range(1, count + 1))
                or any(row["cpu_ns"] < 0 for row in rows)):
            raise ValueError("Inconsistent finalist timing or branch index")
    if {row["branch"]: row["score"] for row in completed if row["score"] is not None} != {
        index: score for index, score in enumerate(decisions, 1) if score is not None
    }:
        raise ValueError("Completed scores differ from the ordered finalist results")
    victor = min((score, index) for index, score in enumerate(decisions, 1) if score is not None)[1]
    if victor != trace["branch"]:
        raise ValueError("Winner differs from the original scores or tie rule")
    winner, = [row for row in completed if row["branch"] == victor]
    prefix_ns = sum(row["cpu_ns"] for row in prefixes if row["branch"] == victor)
    winner_ns = prefix_ns + winner["cpu_ns"]
    measured_ns = sum(row["cpu_ns"] for row in [*prefixes, *completed])
    unitemized_ns = cold_ns - (rank_ns or 0) - measured_ns
    if unitemized_ns < 0 or (rank_ns is not None and rank_ns < 0):
        raise ValueError("Rank and disjoint fit costs exceed the enclosing cold stage")
    finite_prefixes = [(row["score"], row["branch"]) for row in prefixes if row["score"] is not None]
    return dict(cold_cpu_ns=cold_ns, rank_cpu_ns=rank_ns, ranked_finalists=count, winner=victor,
                prefix_leader=min(finite_prefixes)[1] if finite_prefixes else None,
                winner_prefix_cpu_ns=prefix_ns, winner_finish_cpu_ns=winner["cpu_ns"],
                winner_evaluations=[winner["first_evaluations"], winner["second_evaluations"]],
                original_finalist_routing=trace["routing"],
                competitor_cpu_ns=measured_ns - winner_ns, unitemized_cpu_ns=unitemized_ns,
                first_incumbent_wins=victor == 1,
                optimistic_saving_cpu_ns=cold_ns - (rank_ns or 0) - winner_ns if victor == 1 else 0)


def route(trace, terminal, rank_ns=None):
    if trace["receipt"]["decision"] != "complete" or trace["receipt"]["terminal_sha256"] != terminal:
        raise ValueError("The saved trace differs from the verified publication")
    details = trace["route_details"]
    return account(round(details["cold_clocks"]["cpu_s"] * 1e9), details["cold"], rank_ns)


def collect():
    results = {}
    for offer, pins in WEAK.items():
        root = Path(f"/dev/shm/leo-v3-portable-repaired-0016-{offer}-01")
        trace = checked(root / "portable/selective/joint-research-receipt.json", pins[0])
        summary = checked(root / "complete-scope.json", pins[1])
        portable = summary["runs"]["portable"]
        if not summary["same_science"] or not summary["same_regional_evidence"]:
            raise ValueError("Weak publication comparison is incomplete")
        results[f"DS30-0016 {offer}"] = route(trace, portable["science"]["terminal_sha256"]) | dict(
            native_sha256=summary["native_sha256"], terminal=portable["science"]["terminal_sha256"],
            omitted=summary["offer_omits_reference"], known_false_fix=portable["false_fix"],
            horizontal_error_km=portable["horizontal_error_km"],
            owners=portable["science"]["products"]["owner_counts"], source_sha256=list(pins))

    root = Path("/dev/shm/leo-v3-block-portable-0316-result01")
    trace = checked(root / "portable/joint-research-receipt.json", MEDIUM["publication"])
    rank, = checked(root / "rank.json", MEDIUM["rank"])["evaluations"]
    summary = checked(root / "combined-verified.json", MEDIUM["verification"])
    science = summary["scientific"]
    terminal = "sha256:" + science["terminal.json"]
    results["DS30-0316 portable plus blocks"] = route(trace, terminal, rank["rank"]["cpu_ns"]) | dict(
        terminal=terminal, native_sha256="sha256:" + science["detections.json"],
        ordered_rank_count=rank["nodes"], ordered_rank_sha256=rank["digest"],
        horizontal_error_km=summary["geography"]["runs"]["candidate"]["horizontal_error_km"],
        owners=science["owner_counts"], source_sha256=MEDIUM)

    root = Path("/dev/shm/leo-v3-mixed-final-0008-01")
    trace = checked(root / "candidate/joint-research-receipt.json", DENSE["publication"])
    summary = checked(root / "result.json", DENSE["verification"])
    archive = checked(HERE / "measurements/cold-exact-budget-dense-control.json.gz", DENSE["rank_trace"])
    rank = checked(HERE / "measurements/cold-exact-budget-dense-control-binding.json.gz", DENSE["rank_binding"])
    work = archive["stages"]["work"]
    current, previous = trace["route_details"]["cold"], work["selected"]
    if (without_clocks(current) != without_clocks(previous) or archive["binding_sha256"] != DENSE["rank_binding"]
            or trace["receipt"] != summary["worker"]["receipt"] or not summary["verified"]
            or any(rank["request"][left] != summary["inputs"][right] for left, right in
                   (("native_file", "packet"), ("offer_sha256", "offer_sha256"), ("inventory", "inventory"),
                    ("causal_cutoff_utc_ns", "cutoff_utc_ns"), ("local_archive", "archive")))):
        raise ValueError("The independent dense rank timer does not match the current cold result")
    signatures = [sha256(json.dumps(node, separators=(",", ":")).encode()).hexdigest() for node in work["ordered"]]
    if len(set(signatures)) != len(signatures):
        raise ValueError("Repeated ordered rank identity in the dense control")
    cold_scope, = work["scopes"]
    rank_scope, = work["ranks"]
    budget = account(cold_scope["cpu_ns"], previous, rank_scope["cpu_ns"])
    terminal = summary["terminal_sha256"]
    results["DS30-0008 mixed"] = route(trace, terminal) | dict(
        terminal=terminal, native_sha256=summary["inputs"]["native"], ordered_signature_sha256=signatures,
        independent_ranked_control=budget,
        horizontal_error_km={arm: row["position_error_km"] for arm, row in summary["solution"].items()},
        owners={arm: row["candidate"] for arm, row in summary["ownership"].items()}, source_sha256=DENSE)

    for row in results.values():
        row["decision_ceiling_cpu_ns"] = row.get("independent_ranked_control", row)["optimistic_saving_cpu_ns"]
    return dict(threshold_cpu_ns=THRESHOLD_NS, cases=results, new_solver_runs=0, waveform_reads=0,
                clears_threshold=any(row["decision_ceiling_cpu_ns"] > THRESHOLD_NS for row in results.values()))


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2, sort_keys=True, allow_nan=False))
