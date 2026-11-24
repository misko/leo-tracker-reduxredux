"""Verify the signed tiny withholding and reduce the matched physical gates."""

import argparse
import json
from pathlib import Path
from statistics import median
import sys

from legacy_block_raw_0107 import HERE, POSITIVE, POSITIVE_PIN, checked_json, released_paths
from legacy_block_0107_metadata import digest


MODES = ("ordinary", "indexed")
ARMS = ("c0", "fitted_c")


def read(path):
    return json.loads(path.read_bytes())


def speedup_gate(baselines, outputs):
    if set(baselines) != set(outputs) or len(baselines) != 2 or min(*baselines.values(), *outputs.values()) <= 0:
        raise ValueError("Require two successful, paid, paired comparisons")
    ratios = {label: outputs[label]/baselines[label] for label in baselines}
    middle = median(ratios.values())
    sum_ratio = sum(outputs.values())/sum(baselines.values())
    gates = {key: dict(median=middle <= cutoff, sum=sum_ratio <= cutoff, both=max(middle, sum_ratio) <= cutoff)
             for key, cutoff in (("1.6x", .625), ("2x", .5))}
    return dict(ratios=ratios, baseline_s=sum(baselines.values()), indexed_s=sum(outputs.values()),
                median_speedup=1/middle, summed_speedup=1/sum_ratio, gates=gates)


def snapshot(folder, process, req):
    from empty_bootstrap import bind_native
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification.paired_publication import evidence

    raw = read(folder/"unified-short-bootstrap.json")
    witness = read(folder/"exact-named-raw-witness.json")
    native_path, = folder.glob("fast-scan-automatic-work/*/detections.json")
    native = read(native_path)
    bind_native(native, req["session"], req["inventory"], req["detector"][7:], expected=req["native"])
    receipt = raw["receipt"]
    verified = evidence(folder, receipt, process["started_unix_ns"], read_only=True)
    store = FastStandardAnalysisStore(folder)
    run = receipt["run_id"]
    terminal = read(folder/"fast-scan-automatic-work"/run/"terminal.json")
    probes = native["source"]["probes"]
    factors = sum(len(row["candidates"]) for row in probes)
    if (process["exit_code"] or (receipt["window_count"], len(probes), factors) != (29, 54, 19)
            or receipt["counts"] != dict(processed=27, invalid_capture=2, skipped_fast_score=0)
            or receipt["decision"] != "withheld" or verified["reason"] != "no_active_curvature"
            or verified["raw_authority"] != req["authority"] or raw["native_sha256"] != req["native"]
            or "sha256:"+digest(native_path.read_bytes()) != req["native"]
            or raw["requested_offer_sha256"] != req["offer_sha256"] or raw["archive_root"] != req["archive"]["root"]
            or raw["causal_cutoff_utc_ns"] != req["cutoff_utc_ns"] or raw["raw_acquisitions"] != 1
            or raw["verified_handoffs"] != 1 or raw["scientific_imports_before"] or raw["scientific_imports_after"]
            or raw["receiver_audit"]["native"]["visits"] != dict(full=8, short_primary=19)
            or not raw["graph_proof"]["proven"] or witness["ports"] is not None or witness["evidence"]["images"]
            or store.position_path(run) is not None or store.position_grid(run) is not None or list(folder.rglob("*.png"))
            or set(terminal["arms"]) != set(ARMS)
            or any(pt["latlon"] is not None or pt.get("rf_rms_hz") is not None for pt in terminal["arms"].values())):
        raise ValueError("The full native proof and both null arms must match the genuine original empty publication")
    report = folder/"fast-scan-reports"/(run+".json")
    return dict(native_digest=raw["native_sha256"], science=verified, terminal=terminal,
                scan_digest=digest(report.read_bytes()), graph_proof=raw["graph_proof"],
                opportunities=len(probes), factors=factors, phases=raw["phases"],
                receiver_visits=raw["receiver_audit"]["native"]["visits"], witness=witness)


def prices(weak, tiny, clocks):
    result = {}
    for metric in ("elapsed_s", "cpu_s"):
        large = weak["prices"][metric]
        small_ready = clocks["indexed"][metric]+tiny["ready_checks"][metric]
        named = {"DS30-0016": large["installed_prior"], "DS30-0107": tiny["installed_prior"][metric]}
        ordinary = {"DS30-0016": large["ordinary"], "DS30-0107": clocks["ordinary"][metric]}
        bare = {"DS30-0016": large["prepared"]-weak["admission"]["ready_checks"][metric], "DS30-0107": clocks["indexed"][metric]}
        ready = {"DS30-0016": large["prepared"], "DS30-0107": small_ready}
        common = {"DS30-0016": weak["admission"]["shared_admission"][metric], "DS30-0107": tiny["shared_admission"][metric]}
        with_custody = {case: ready[case]+common[case] for case in ready}
        first = {"DS30-0016": large["first_use"], "DS30-0107": small_ready+tiny["preparation"]["clock"][metric]}
        result[metric] = dict(ordinary=ordinary, installed_historical=named, indexed=dict(child=bare, ready=ready, with_custody=with_custody,
            first_use_map=first, two_first_use_plus_shared_portable_producer_s=sum(first.values())+large["earlier_portable_preparation"]),
            ordinary_child=speedup_gate(ordinary, bare), ordinary_ready=speedup_gate(ordinary, ready),
            ordinary_ready_with_common=speedup_gate({key: ordinary[key]+common[key] for key in ordinary}, with_custody),
            named_child=speedup_gate(named, bare), named_ready=speedup_gate(named, ready),
            named_with_custody=speedup_gate(named, with_custody), named_first_use_map=speedup_gate(named, first))
    return result


def score(root):
    sys.path.insert(0, str(HERE.parents[2]/"src"))
    released_paths()
    from aperture_trial import write
    from legacy_block_raw_0016 import seal

    verified = read(root/"prediction-seal.json")
    if verified != seal(root):
        raise ValueError("The full timed comparison changed")
    book = read(root/"admission.json")
    req = book["metadata"]["request"]
    reports, clocks = {}, {}
    for mode in MODES:
        log = read(root/(mode+"-clock.json"))
        if log["command"] != book["commands"][mode]:
            raise ValueError("Measured worker differs from the signed shared options")
        clocks[mode] = log["clock"]
        reports[mode] = snapshot(root/mode, log["clock"], req)
    ordinary, indexed = (reports[mode] for mode in MODES)
    historical = snapshot(Path("/dev/shm/leo-v3-history-risk-0107-cairo-result01/candidate"),
                          read(Path("/dev/shm/leo-v3-history-risk-0107-cairo-result01/candidate-clock.json"))["clock"], req)
    for key in ("native_digest", "terminal", "scan_digest", "graph_proof", "receiver_visits"):
        if ordinary[key] != indexed[key] or ordinary[key] != historical[key]:
            raise ValueError(f"The genuine historical withholding output changed: {key}")
    if (root/"ordinary/legacy-map-acquisition.json").exists():
        raise ValueError("The ordinary comparison must use the untouched reader")
    usage = read(root/"indexed/legacy-map-acquisition.json")
    row, = usage["members"]
    expected, = book["plan"]["members"]
    if (any(row[k] != val for k, val in expected.items()) or usage["custody_sha256"] != book["map_custody_sha256"]
            or usage["binary_sha256"] != book["preparation"]["decoder_binary_sha256"]
            or row["authenticated_encoded_bytes"] != expected["encoded"] or row["kind"] != ("map" if row["map"] else "ordinary")
            or row["map"] and row["counts"] != dict(full=8, prefix=19, committed_bytes=24_960_000)
            or not row["map"] and row["committed_bytes"] != expected["decoded"]):
        raise ValueError("One exact signed member must be authenticated with explicit active-map or fallback counts")
    weak = checked_json(POSITIVE/"result.json", POSITIVE_PIN)
    write(root/"result.json", dict(qualified=True, case="DS30-0107", paired=reports, clocks=clocks, admission=book,
          geometry=book["metadata"]["geometry"], prior_verified_terminal=historical["terminal"], reader_audit=usage,
          cohort=prices(weak, book, clocks), positive_receipt_sha256=POSITIVE_PIN,
          prediction_seal_sha256=digest((root/"prediction-seal.json").read_bytes())))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    score(cli.parse_args().root)
