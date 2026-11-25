"""Bound installed-science ports from the frozen first 64 signed DS30 clocks."""

import argparse
from collections import Counter
from gzip import compress, decompress
import json
from math import fsum
from pathlib import Path
import sys

from .ds30_routing_first64 import BOUNDARY, CASE_KEY, EXPORT, LIMIT, SEAL, restricted_json
from .field_speed_reachability import PLAN, STOCK, checked, digest
from .first64_producer_transfer import FROZEN_CLOCK, ROSTER, ROUTING
from .installed_receiver_first30 import DONOR, DONOR_PIN, SOURCE, clock_spans, no_backing, one, ratios
from .receiver_solver_targets import required_reduction


MEASUREMENTS = Path(__file__).parent / "measurements"
FIRST30 = "164da2b6c62ee9e6b60b4918ce937d8d37475808b53d8e5f3269be30c70a7153"
NAMED = "ffabb26e6e518afc44e026396efa06ce28609e1380223090bfb2bb6a85902b43"
CAIRO = "627c3aaa693499ae293879f4912f3b4425f82e6feaefd4f9ea44e15d2e7558a0"
PAYLOAD = Path("/opt/leo-algo08/algo08v3/payload")
LOOKAHEAD = "tools/pipeline_eval/variants/experimental/receiver_member_lookahead.py"
PUBLICATION = "tools/pipeline_eval/qualification/experimental_publication.py"
PREFIX_BYTES = 16 << 20


def receipt(path, pin):
    data = checked(path, pin)
    return json.loads(decompress(data) if path.suffix == ".gz" else data)


def installed_source():
    for path, pin in SOURCE.items():
        checked(path, pin)
    spec = json.loads((PAYLOAD / "spec.json").read_bytes())
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False)
    if digest(canonical.encode()) != STOCK:
        raise ValueError("The installed specification differs from the field executable")
    named = [LOOKAHEAD, PUBLICATION, "png-filter.so", "png-deflate.so", "posterior-grid-handoff.so"]
    for name in named:
        checked(PAYLOAD / name, spec["sources"][name])
    flags = ("ingress", "schedule", "rendering", "solver", "member_lookahead", "posterior_grid_handoff",
             "graph_path", "sparse_rank_projection", "endpoint_reuse", "curved_design", "recovery_reuse", "tle_parser")
    return dict(specification_sha256=STOCK, flags={key: spec[key] for key in flags},
                sources={key: spec["sources"][key] for key in named},
                source_bytes_per_hint=PREFIX_BYTES, asynchronous_owned_snapshot_pool=False,
                cairo_layout=False)


def clock_rows(snapshot, campaign):
    plan = receipt(campaign / "plan.json", PLAN)
    seal = receipt(snapshot / "seal.json", SEAL)
    known = receipt(FROZEN_CLOCK, ROUTING)["measurements"]
    order = list(dict.fromkeys([*plan["smoke"], *(row["case"] for row in plan["cases"])]))
    prefix = order[:LIMIT]
    if (digest(("\n".join(prefix) + "\n").encode()) != ROSTER or order[LIMIT] != BOUNDARY
        or [row["case"] for row in known] != prefix or seal["combined_sha256"] != EXPORT
        or seal["plan_sha256"] != "sha256:" + PLAN or plan["cpu"] != 2):
        raise ValueError("Expected the independent frozen pre-0218 one-core checkpoint")
    selected = {}
    for line in restricted_json(checked(snapshot / "rows.jsonl", EXPORT).splitlines(), CASE_KEY, prefix):
        row = json.loads(line)
        if row["algorithm"] == "installed":
            if row["case"] in selected:
                raise ValueError("Ambiguous selected installed attempt")
            selected[row["case"]] = row, "sha256:" + digest(line)
    if len(selected) != LIMIT:
        raise ValueError("Missing original measurement")
    for proof in known:
        row, line_pin = selected[proof["case"]]
        bound = proof["installed"]
        if (line_pin != bound["export_line_sha256"] or row["attempt_result_sha256"] != bound["attempt_result_sha256"]
            or row["build_sha256"] != "sha256:" + STOCK or not row["verified_pair"] or not row["acquisition_verified"]
            or row.get("relocation_proof_sha256") != seal["proofs"].get(row["case"])):
            raise ValueError("Selected installed attempt differs from its sealed checkpoint")
        yield stock_clock(campaign, row)


def stock_clock(campaign, row):
    path = (campaign / row["attempt"]).resolve(strict=True)
    if not path.is_relative_to(campaign):
        raise ValueError("Installed clock receipt left campaign custody")
    record = receipt(path, row["attempt_result_sha256"])
    if (record["outcome"] != row["outcome"] or record["elapsed_s"] != row["elapsed_s"]
        or record["cpu_s"] != row["cpu_s"] or record["timing_scope"] != row["timing_scope"]
        or record["native_sha256"] is None or record["process"]["started_unix_ns"] != row["child_started_unix_ns"]
        or record["process"]["finished_unix_ns"] != row["child_finished_unix_ns"]):
        raise ValueError("Timing or native production differs from the original charged attempt")
    publication = path.parent / "publication"
    identity = record["raw_identity"]
    signed = record["evidence"]["receipt"]
    if (identity["raw_authority_sha256"] != row["raw_authority_sha256"] or
        identity["session_id"] != signed["session_id"] or row["window_count"] != signed["window_count"]):
        raise ValueError("Authenticated original output identity changed")
    # Only stat the prior verified native and terminal artifacts. Their payloads
    # and reference coordinates are deliberately outside the timing audit.
    native = one(publication, "fast-scan-automatic-work/*/detections.json")
    inventory = one(publication, "fast-scan-inputs/*.json")
    checked(inventory, identity["inventory_sha256"])
    terminal = None
    if row["outcome"] != "solver_failed":
        mark = json.loads((publication / "algo08v3-release.json").read_bytes())
        if (mark["frozen_specification"] != "sha256:" + STOCK or mark["decision"] != row["outcome"]
            or mark["session_id"] != identity["session_id"] or signed["terminal_sha256"] != row["terminal_sha256"]):
            raise ValueError("Retained installed terminal differs from the verified original")
        terminal = one(publication, f"fast-scan-automatic-work/{signed['run_id']}/terminal.json").stat().st_mtime_ns
    elif not record["reached_solver"] or any(publication.glob("fast-scan-automatic-work/*/terminal.json")):
        raise ValueError("Installed failure must retain its actual post-detector charged exit")
    stamps = dict(native=native.stat().st_mtime_ns, inventory=inventory.stat().st_mtime_ns, terminal=terminal)
    phases = clock_spans(record, *stamps.values())
    hints = signed.get("member_lookahead")
    if hints and not (0 <= hints["submitted"] <= hints["attempts"]
                      and 0 <= hints["submitted_bytes"] <= PREFIX_BYTES*hints["submitted"]
                      and 0 <= hints["cpu_ns"]/1e9 <= phases["through_native_write"]):
        raise ValueError("Reported hints exceed their witnessed serial scope")
    active = ("screened_nomination", "sparse_rank_projection", "graph_path", "tle_records", "endpoint_reuse",
              "recovery_reuse", "curved_design", "posterior_grid_handoff")
    return dict(case=row["case"], outcome=row["outcome"], wall=row["elapsed_s"], cpu=row["cpu_s"],
                original=row["raw_authority_sha256"], result=row["attempt_result_sha256"],
                native=record["native_sha256"], stamps=stamps, phases=phases, lookahead=hints,
                activations={key: signed[key] for key in active if key in signed})


def price(cases):
    baseline = [row["wall"] for row in cases]
    prefix = [row["phases"]["through_native_write"] for row in cases]
    pre_cpu = [row["phases"]["prefix_cpu_bound"]["lower"] for row in cases]
    hint = [(row["lookahead"] or {}).get("cpu_ns", 0)/1e9 for row in cases]
    open_upper = [max(0., cpu-cost) if row["lookahead"] is not None else 0.
                  for row, cpu, cost in zip(cases, pre_cpu, hint, strict=True)]
    suffix_tail = [row["phases"]["terminal_to_exit"]+row["phases"]["verifier"] for row in cases]
    solver = [row["phases"]["inventory_to_terminal_write"]+row["phases"]["inventory_to_failed_exit"] for row in cases]
    half = fsum(baseline)/2
    scenarios = dict(measured=baseline, free_render_tail_and_verifier=[a-b for a,b in zip(baseline,suffix_tail,strict=True)],
                     free_everything_after_native=prefix, free_waits_and_everything_after_native=pre_cpu,
                     additionally_free_all_hint_cpu_and_missing_hint_rows=open_upper)
    comparison = {key: ratios(baseline, values) | dict(sum_gap_s=fsum(values)-half)
                  for key, values in scenarios.items()}
    count_names = ("through_native_write", "native_to_inventory_write", "inventory_to_terminal_write",
                   "inventory_to_failed_exit", "terminal_to_exit", "verifier")
    return dict(half=half, joint_gates=comparison, measured_caps={key: fsum(row["phases"][key] for row in cases)
                                                                 for key in count_names},
                reported_hint_cpu_s=fsum(hint), hint_bytes=sum((row["lookahead"] or {}).get("submitted_bytes", 0)
                                                              for row in cases),
                reported_hint_rows=sum(row["lookahead"] is not None for row in cases),
                additional_prefix_cpu_s=max(0., fsum(pre_cpu)-half),
                conditional_donor_solver_pool_s=fsum(solver),
                per_case=[dict(case=row["case"], half=base/2, prefix_wall=bound, prefix_cpu_lower=cpu,
                               solver_cap=solve, render_verifier_cap=tail)
                          for row, base, bound, cpu, solve, tail in zip(cases, baseline, prefix, pre_cpu,
                                                                       solver, suffix_tail, strict=True)])


def donors():
    exact = receipt(DONOR, DONOR_PIN)
    if not exact["qualified"] or not all(exact["science_exact"][key] for key in ("arms", "owners", "grid", "path", "terminal")):
        raise ValueError("Expected the verified unchanged-native positive physical control")
    acqu = exact["candidate"]["phases"]["authenticated_raw_acquisition"]
    stock = exact["stock_archival"]["process"]["clock"]
    child = exact["process"]["clock"]
    verify = exact["validation"]
    panel = receipt(MEASUREMENTS / "exact-named-saved-panel-four.json", NAMED)
    cairo = receipt(MEASUREMENTS / "exact-named-cairo.json.gz", CAIRO)
    saved = {case: {"parity": row["parity"], "clocks": {
        role: {key: clock[key] for key in ("cpu_s", "elapsed_s")}
        for role, clock in row["clocks"].items()}} for case, row in panel["per_case"].items()}
    if panel["exact_cases"] != len(saved) or not all(all(r["parity"].values()) for r in saved.values()):
        raise ValueError("Held exact named port does not have complete scientific and media parity")
    return dict(physical_0016=dict(raw_clock=child, verification=verify, historic_installed_raw=stock,
                 acquired=acqu, saved_science_checks=exact["science_exact"], receipt_sha256=DONOR_PIN),
                same_packet_exact_named=saved, saved_panel_sha256=NAMED,
                cairo_report_pinned=bool(cairo["matching_reference_scene"]), cairo_sha256=CAIRO)


def splice_frontier(cases, fraction):
    """Apply a saved-solver rate once, then gift the terminal tail as a ceiling."""
    if not 0 <= fraction <= 1:
        raise ValueError("Expected one fraction of the original observed solver scope")
    baseline, raw, modeled, records = [], [], [], []
    for c in cases:
        p = c["phases"]
        prefix = p["through_native_write"]
        solver = p["inventory_to_terminal_write"] * fraction if c["outcome"] == "complete" else 0.
        free_tail = p["terminal_to_exit"] + p["verifier"]
        remain = c["wall"] - solver - free_tail
        baseline.append(c["wall"])
        raw.append(prefix)
        modeled.append(remain)
        records.append(dict(case=c["case"], before=c["wall"], hint_cpu=(c["lookahead"] or {}).get("cpu_ns",0)/1e9,
                            solver_model=solver, independent_free_tail=free_tail,
                            required_prefix_wall_s=max(0., remain-c["wall"]/2)))
    def at(reduction):
        return ratios(baseline, [full-reduction*prefix for full,prefix in zip(modeled,raw,strict=True)])

    need = {gate: required_reduction(lambda cut: at(cut)[gate] <= .5) for gate in ("paired_median", "summed")}
    fraction_needed = max(need.values()) if None not in need.values() else None
    return dict(donor_fraction=fraction, free_tail_ceiling=at(0.), paid_prefix_at_free_tail=fsum(raw),
                scope_ceiling_gap=fsum(modeled)-fsum(baseline)/2,
                required_uniform_prefix_fraction=need | {"both": fraction_needed},
                required_uniform_prefix_speedup=None if fraction_needed in (None,1.) else 1/(1-fraction_needed),
                per_case=records)


def report(snapshot, campaign):
    src = installed_source()
    cases = list(clock_rows(snapshot, campaign))
    old = receipt(MEASUREMENTS / "installed-receiver-first30.json.gz", FIRST30)["cases"]
    if [(v["case"],v["result"],v["stamps"],v["phases"]) for v in cases[:30]] != [
        (v["case"],v["result"],v["timestamps"],v["phases"]) for v in old]:
        raise ValueError("First-30 checkpoint no longer reproduces its original marker scopes")
    base = price(cases)
    donor = donors()
    dense = donor["same_packet_exact_named"]["DS30-0374"]["clocks"]
    fraction = 1 - dense["candidate"]["elapsed_s"] / dense["named"]["elapsed_s"]
    activation = Counter(key for row in cases for key in row["activations"])
    activation["positive_grid_factor_count"] = sum(bool(row["activations"].get("posterior_grid_handoff", {}).get("factor_calls"))
                                                    for row in cases)
    return dict(snapshot=dict(plan=PLAN, export=EXPORT, seal=SEAL, first30_regression=FIRST30, roster_sha256=ROSTER),
                installed_source=src, origins=Counter(row["outcome"] for row in cases), activation=activation,
                costs=base, donors=donor, conditional_ordinary_splice=splice_frontier(cases, fraction),
                source_sha256=digest(Path(__file__).read_bytes()), cases=cases,
                waveform_reads=0, catalogue_reads=0, receiver_calls=0, solver_calls=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("snapshot", "campaign", "output"):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    sys.addaudithook(no_backing)
    data = report(args.snapshot, args.campaign.resolve(strict=True))
    with args.output.open("xb") as stream:
        stream.write(compress(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(), mtime=0))
