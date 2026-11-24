"""Bind three archival detector paths and price exact JSON work without a timing run."""

from hashlib import sha256
from pathlib import Path
import argparse
import gzip
import json

from native_packet_bytes import NativePacketBytes


HERE = Path(__file__).resolve().parent
CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
WEAK = Path("/dev/shm/leo-v3-integrated-original-02/DS30-0016/candidate")
WEAK_STOCK = Path("/dev/shm/leo-v3-stock-raw-repeat-DS30-0016-01/stock")
CHARTED_RELEASE = "b54ea21044d6ba5bab285cba777cd4b90a79faf9"
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
PINS = {
    "integrated-original.json.gz": "eb115ec1dd7a734693e21d8be49e2f7de87fe48936b8db8d51e1216cf37a0dff",
    "stock-raw-repeat-0016.json.gz": "e852ffcf8b887e7cab66bcb5f8ad4911caaaa9398264d3b5f351b02862b17850",
    "full-short-seal-scaling.json": "ef8285073952da534c7f02cc33c398eea75df17f3ed7f092a24faa31eddc23d5",
    "source-manifest.json": "4ccea346e610ac46cbcf1a1b00c2df10281f5d4bcd6136441879dcb7f29a4f2b",
}
SOURCES = {
    "tools/algo08_scan.py": "573d6608597f1619785688769e7504a4ad8ac30dd71fecd37876c678ed4aca53",
    "src/leo/storage/fast_scan.py": "db79b4e50c10a3b948c69c86a464fb57a226b0dbb2955cf90d8ae83db3f39527",
    "src/leo/contracts/digests.py": "9cf74423dd2eb0e2b66d5b3b955e438d28260d6b22e53281ae2e1481da9dd9b9",
}
ATTEMPTS = {
    "DS30-0049": (2, ("724b4bb7f4712408743c302618ada557a26b599b30b99b21cdfc4c12cc861cc2",
                     "dd123ba20c9c7ecfcec3736469c1b85e11fa0eeb6b49455c0df3faddc05aa5fa")),
    "DS30-0274": (1, ("6b7dcc00ec5fecf6449db306912d3bd26fd5985d1e53e8163feba108c07ed742",
                     "dd5cdd80ee1ea48a27792b0d488746c2aca2ca5ffcfbb8aaa9b1dbe1db44fee1")),
}


def read(path, pin=None):
    body = path.read_bytes()
    if pin and sha256(body).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Saved artifact changed at {path}")
    return body


def document(path, pin=None):
    body = read(path, pin)
    return json.loads(gzip.decompress(body) if path.suffix == ".gz" else body)


def calibration():
    path = HERE/"measurements/full-short-seal-scaling.json"
    pairs = document(path, PINS[path.name])["calibration"]["pairs"]
    measurements = []
    for pair in pairs:
        for row in pair:
            if row["arm"] != "full":
                continue
            measurements.append(dict(bytes=row["bytes_written"], **{
                name: row["stages"][name]["cpu_ns"] for name in
                ("canonical_json", "parse", "readback", "source_verification")}))
    if len(measurements) != 2:
        raise ValueError("Expected the two existing full-file seal repetitions")
    return measurements


def native_file(output, expected, encode):
    path, = (output/"fast-scan-automatic-work").glob("*/detections.json")
    native = json.loads(read(path, expected))
    captured = NativePacketBytes.capture(native, encode)
    payload, digest = captured.verified_readback(path)
    if digest != expected:
        raise ValueError("Canonical and persisted detection identities differ")
    source, origin = native["source"], native["provenance"]
    probes = source["probes"]
    analysis = encode(["cancellation",source["raw_recording_authority_digest"],
                       origin["detector_sha256"][7:],probes])
    if "sha256:"+sha256(analysis).hexdigest() != source["analysis_manifest_sha256"]:
        raise ValueError("Published native rows lost their distinct analysis binding")
    terminal, = (output/"fast-scan-automatic-work").glob("*/terminal.json")
    data = document(terminal)
    if data["native_sha256"] != digest or data["decision"] != "ok":
        raise ValueError("Expected an actual terminal bound to the exact original file")
    return native, dict(bytes=len(payload), sha256=digest, analysis_bytes=len(analysis),
                        terminal_sha256=NativePacketBytes.capture(data,encode).sha256,
                        probes=len(probes), factors=sum(len(probe["candidates"]) for probe in probes))


def readback_clocks(raw, exact, control):
    phases = raw["phases"]
    included = ("receiver_ready_from_entry", "asset_and_inventory_checks", "authenticated_raw_acquisition",
                "held_anchor_route_selection", "decision_and_publication")
    timing = exact["timing"]
    if any(len(timing[k]) != 1 for k in ("analyze", "solve", "render")):
        raise ValueError("Need the genuine one-solve standard publication")
    clocks = {}
    for clock, ns in (("cpu_s","cpu_ns"),("elapsed_s","wall_ns")):
        analyze = timing["analyze"][0][clock]
        solve, render = timing["solve"][0][clock], timing["render"][0][clock]
        scopes = dict(acquisition_wrapper_remainder_s=phases["authenticated_raw_acquisition"][clock]
                        -raw["receiver_audit"]["acquire"][ns]/1e9,
                      held_route_selection_s=phases["held_anchor_route_selection"][clock],
                      scan_analyze_excluding_solve_render_s=analyze-solve-render,
                      exact_evidence_with_artifacts_s=exact["verification"][clock],
                      bootstrap_unassigned_to_receipt_s=raw["total_before_receipt"][clock]
                        -sum(phases[k][clock] for k in included))
        if control is not None:
            scopes["controller_independent_publication_s"] = control[clock]
        if min(scopes.values()) < 0:
            raise ValueError("Unexpected overlapping timing scopes")
        clocks[clock] = scopes
    return clocks


def row(case, archives, raw, exact, encode, cost):
    stock, successor = archives
    base, stock_info = native_file(stock["output"],stock["digest"],encode)
    selected, short_info = native_file(successor["output"],successor["digest"],encode)
    fields = ("session_id", "raw_recording_authority_digest", "input_manifest_sha256")
    if any(base["source"][k] != selected["source"][k] for k in fields):
        raise ValueError("The two receiver packets do not bind the same original")
    held = raw["held_anchor_route"]
    prior_recipe = {k:v for k,v in held["receiver_recipe"].items() if k != "held_native_8ms"}
    src = selected["source"]
    base_detector = NativePacketBytes.capture(prior_recipe,encode).sha256
    parent_preimage = encode(["cancellation",src["raw_recording_authority_digest"],
                              base_detector[7:],src["probes"]])
    parent_analysis = "sha256:"+sha256(parent_preimage).hexdigest()
    parent = dict(selected,source=dict(src,analysis_manifest_sha256=parent_analysis),
                  provenance=dict(selected["provenance"],detector_sha256=base_detector,
                                  run_id="blind-compact-"+parent_analysis[7:39]))
    if (held["choice"]["route"] != "unfiltered" or held["native_sha256"] != successor["digest"]
            or held["refinement_calls"] or held["parent_detector_sha256"] != base_detector
            or held["parent_native_sha256"] != NativePacketBytes.capture(parent,encode).sha256
            or raw["native_sha256"] != successor["digest"]
            or exact["evidence"]["detail"]["input_sha256"] != successor["digest"]
            or raw["receiver_audit"]["analysis_manifest"] != parent_analysis):
        raise ValueError("Could not reconstruct the independently committed pre-held original rows")
    scales = {name: max(x[name] / x["bytes"] for x in cost) for name in
              ("canonical_json", "parse", "readback", "source_verification")}
    # Conservative byte-normalized extrapolation from the two archived 5.59 MB
    # seals. Do not substitute parent phase costs for JSON-specific clocks.
    for info, role in ((stock_info,stock),(short_info,successor)):
        info["process"] = role["process"]
        info["controller_validation"] = role["validation"]
        info["estimated_cpu_ms_per_pass"] = {name: slope*info["bytes"]/1e6 for name,slope in scales.items()}
    estimates = short_info["estimated_cpu_ms_per_pass"]
    sensitivity = dict(
        one_selected_reencode=estimates["canonical_json"],
        six_selected_reencodes_and_five_probe_bindings=6*estimates["canonical_json"]+5*estimates["source_verification"],
        one_stock_terminal_reencode=stock_info["estimated_cpu_ms_per_pass"]["canonical_json"],
    )
    return dict(case=case,installed=stock_info,successor=short_info,
                pre_held=dict(bytes=len(encode(parent)),sha256=held["parent_native_sha256"],
                              analysis_bytes=len(parent_preimage),analysis_sha256=parent_analysis),
                ordered_original_scope=selected["provenance"]["window_count"],
                estimated_ms_after_free_reuse=sensitivity,
                successor_disjoint_limits=readback_clocks(raw,exact,successor["validation"]))


def run(campaign):
    from leo.contracts.digests import canonical_json_bytes

    if Path(canonical_json_bytes.__code__.co_filename).resolve() != RELEASE/"src/leo/contracts/digests.py":
        raise ValueError("Expected the exact deployed canonical JSON encoder")
    for source,pin in SOURCES.items():
        read(RELEASE/source,pin)
    read(Path("/opt/leo-algo08/algo08v3/payload/tools/algo08_scan.py"),SOURCES["tools/algo08_scan.py"])
    manifest = document(campaign/"frozen-build/source-manifest.json",PINS["source-manifest.json"])
    if (manifest["charter_git_commit"] != CHARTED_RELEASE or
            manifest["source_archive_embedded_commit"] != "de7873faacd4b92f73ab1fb7e61168f36390eb16"):
        raise ValueError("Frozen deployed charted entry changed")
    original, stock = (document(HERE/"measurements"/name,PINS[name]) for name in
                       ("integrated-original.json.gz","stock-raw-repeat-0016.json.gz"))
    charted = original["runs"]["positive_first"]["DS30-0016"]["result"]["document"]
    named = stock["stock"]
    weak_scopes = tuple(dict(output=path,digest=digest,process=process,validation=None)
                        for path,digest,process in ((WEAK_STOCK,named["digest"],named["process"]["clock"]),
                            (WEAK,charted["receiver"]["native_sha256"],charted["process"])))
    raw = document(WEAK/"unified-short-bootstrap.json")
    if raw != charted["receiver"]:
        raise ValueError("Local development witness differs from its sealed repository archive")
    cost = calibration()
    result = {"DS30-0016": row("DS30-0016",weak_scopes,raw,document(WEAK/"exact-named-raw-witness.json"),
                             canonical_json_bytes,cost)}
    for case,(generation,pins) in ATTEMPTS.items():
        archives, receipts = [], []
        for role,pin in zip(("installed","successor"),pins,strict=True):
            root = campaign/"cases"/case/role/f"attempt-{generation:06d}"
            receipt = document(root/"result.json",pin)
            if receipt["generation"]!=generation or receipt["outcome"]!="complete" or receipt["algorithm"]!=role:
                raise ValueError("Expected completed matched original result")
            receipts.append(receipt)
            archives.append(dict(output=root/"publication",digest=receipt["native_sha256"],
                                 process=receipt["process"],validation=receipt["validation"]))
        if receipts[0]["raw_identity"] != receipts[1]["raw_identity"]:
            raise ValueError("Original paired receipt identity differs")
        output = archives[1]["output"]
        result[case] = row(case,archives,document(output/"unified-short-bootstrap.json"),
                           document(output/"exact-named-raw-witness.json"),canonical_json_bytes,cost)
    return dict(charted=CHARTED_RELEASE,installed_sources=SOURCES,archive_pins=PINS,attempts=ATTEMPTS,
                archived_seal_calibration=cost,results=result,new_gauss_benchmarks=0,waveform_reads=0,solver_runs=0)


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path, default=CAMPAIGN, nargs="?")
    print(json.dumps(run(parser.parse_args().campaign),indent=2,sort_keys=True,allow_nan=False))
