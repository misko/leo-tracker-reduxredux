"""Run the installed named-v3 publication on the original signed saved detector."""

import argparse
from contextlib import ExitStack
from hashlib import file_digest, sha256
import json
from pathlib import Path
import runpy
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from empty_bootstrap import BASELINE, BASELINE_PIN, PAYLOAD, RELEASE, bind_native, checked


PRIOR = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
RESEARCH = Path("/dev/shm/leo-v3-portable-repaired-0016-translated-01")
OFFER_PIN = "063764d149b15b5a61c86a7f02b2a639a564327afdb3dbb32f1ff236e4f5ca6c"
ADMISSION_PIN = "bfd940c22e7cfac17040dbc95e4908ed3224370b5d19d27298d8412afc08e774"
RAW_RESULT_PIN = "348ed9bffa27185f39673bdd0ee20ec2418a9b1e8723f19a950f4e5bd4e399a8"
RESEARCH_PIN = "158b6bcdb065992aca6fcb67db1f5dcee86e925c818bff86222b51f6512ca4be"
NATIVE = "sha256:4c0e22cbc5646e059abf59e968df2ee9d971795204d552adc9223d2426a7a7e0"
PROTOCOL = HERE / "named-0016-translated-protocol.md"


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def one(root, name):
    match, = root.glob(f"fast-scan-automatic-work/*/{name}")
    return match


def check_archive(path, admission):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    refs = TleArchiveReader(path).list_snapshots("space-track")
    if (len(refs) != admission["archive"]["snapshots"] or not refs
            or any(ref.collected_utc_ns >= admission["cutoff_utc_ns"] for ref in refs)
            or canonical_digest({ref.path.name: ref.sha256 for ref in refs}) != admission["archive"]["sha256"]):
        raise ValueError("Expected the original 46 available causal snapshots")
    unique = set()
    for ref in refs:
        stat = ref.path.stat()
        key = stat.st_dev, stat.st_ino, ref.sha256
        if stat.st_dev != path.stat().st_dev or not ref.path.resolve(strict=True).is_relative_to(path):
            raise ValueError("The causal snapshot escaped the staging archive")
        if key not in unique:
            with ref.path.open("rb") as body:
                if file_digest(body, "sha256").hexdigest() != ref.sha256:
                    raise ValueError("A causal snapshot differs from its archived name and digest")
            unique.add(key)
    return dict(count=len(refs), latest_ns=max(ref.collected_utc_ns for ref in refs),
                unique_bodies=len(unique), sha256=admission["archive"]["sha256"])


def validate_packet(native, binding):
    details = binding["admission"]
    detector = details["stock"]["detector_sha256"]
    bind_native(native, details["session"], details["inventory"], detector, expected=NATIVE)
    source, provenance = native["source"], native["provenance"]
    probes = source["probes"]
    if (source["raw_recording_authority_digest"] != details["raw_authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != details["cutoff_utc_ns"]
            or provenance["window_count"] != 808 or provenance["processed_windows"] != 713
            or len(probes) != 1426 or sum(bool(row["candidates"]) for row in probes) != 440):
        raise ValueError("The saved named detector lost original signed capture identity or scope")


def prepare(root):
    from tools.pipeline_eval.qualification.paired_publication import verified_v3
    from portable_omitted_region import translated

    admission = json.loads(checked(PRIOR / "admission.json", ADMISSION_PIN))
    archived = json.loads(checked(PRIOR / "result-final.json", RAW_RESULT_PIN))
    original = archived["original"]["stock"]
    offered = json.loads(checked(RESEARCH / "offer.json", OFFER_PIN))
    if (admission != archived["admission"] or translated(admission["offer"]) != offered
            or original["native_sha256"] != NATIVE or original["process"]["clock"]["exit_code"]
            or admission["stock"] != verified_v3(BASELINE) or admission["case"] != "DS30-0016"):
        raise ValueError("Expected the complete signed named raw publication and original translation")
    archive = PRIOR / "tle"
    for directory in (root.parent, PRIOR, archive, RESEARCH):
        if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", directory], text=True).strip() != "tmpfs":
            raise ValueError("Named packet, archive, offer and outputs must use existing tmpfs")
    inventory = PRIOR / "stock/fast-scan-inputs" / (admission["session"] + ".json")
    packet = one(PRIOR / "stock", "detections.json")
    checked(inventory, admission["inventory"][7:])
    archive_check = check_archive(archive, admission)
    source = {p.name: sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), PROTOCOL)}
    binding = dict(admission=admission, archive=str(archive), archive_check=archive_check, offer=offered,
                   offer_sha256=OFFER_PIN, packet=str(packet), inventory_file=str(inventory), source_sha256=source,
                   original_raw_result_sha256=RAW_RESULT_PIN, launcher_sha256=BASELINE_PIN)
    validate_packet(json.loads(checked(packet, NATIVE[7:])), binding)
    return binding


def child(root):
    binding = read(root / "binding.json")
    for name, pin in binding["source_sha256"].items():
        checked(HERE / name, pin)
    checked(BASELINE, BASELINE_PIN)
    checked(root / "offer.json", OFFER_PIN)
    launcher = runpy.run_path(str(BASELINE))
    sys.path[:0] = [str(PAYLOAD), str(RELEASE / "src"), str(RELEASE)]
    from tools.pipeline_eval.variants.experimental import lean_startup

    original_install = lean_startup.install
    output = root / "translated"
    output.mkdir()
    admission = binding["admission"]
    audit = dict(startup=0, inventory_calls=0, handoffs=0, waveform_attempts=0, selected_packets=[])
    recording = Path(admission["recording"])

    def deny(*args, **kwargs):
        audit["waveform_attempts"] += 1
        raise RuntimeError("The sealed named run cannot read waveform samples")

    def saved(session, inventory_digest, inventory, assets):
        if audit["handoffs"] or (session, inventory_digest) != (admission["session"], admission["inventory"]):
            raise ValueError("Wrong or repeated saved detector handoff")
        native = json.loads(checked(Path(binding["packet"]), NATIVE[7:]))
        validate_packet(native, binding)
        audit["handoffs"] += 1
        return native

    with ExitStack() as stack:
        def install_ports():
            original_install()
            from leo.storage.fast_scan import FastScanStore, FastSegmentSource
            from leo.storage.short_window import ShortWindowReader
            from tools import algo08_position, algo08_scan
            from named_constrained_research import inventory_binding

            if Path(algo08_scan.__file__).resolve() != PAYLOAD / "tools/algo08_scan.py":
                raise ValueError("The installed named scanner is required")
            frozen_inventory = inventory_binding(recording, Path(binding["inventory_file"]), admission["session"],
                                                 admission["inventory"])
            stock_packet = algo08_position.selected_packet

            def inventory(store, path, *, verify_windows=True):
                result = frozen_inventory(store, path, verify_windows=verify_windows)
                audit["inventory_calls"] += 1
                return result

            def observe(*args, **kwargs):
                packet = stock_packet(*args, **kwargs)
                audit["selected_packets"].append({arm: [[str(row["observation_id"]), int(row["norad"]), str(row["role"])]
                                                       for row in rows] for arm, rows in packet["rows"].items()})
                return packet

            stack.enter_context(patch.object(FastScanStore, "inventory", inventory))
            stack.enter_context(patch.object(FastSegmentSource, "__init__", deny))
            stack.enter_context(patch.object(ShortWindowReader, "__init__", deny))
            stack.enter_context(patch.object(algo08_scan, "acquire", saved))
            stack.enter_context(patch.object(algo08_scan, "detector", deny))
            stack.enter_context(patch.object(algo08_position, "selected_packet", observe))
            audit["startup"] += 1

        stack.enter_context(patch.object(lean_startup, "install", install_ports))
        try:
            launcher["main"](["--recording", str(recording), "--archive", binding["archive"], "--region",
                              str(root / "offer.json"), "--bulk-root", str(output)])
        finally:
            write(root / "saved-port.json", audit)


def launch(root):
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    binding = prepare(root)
    binding["machine"] = host()
    root.mkdir()
    (root / "tmp").mkdir()
    (root / "offer.json").write_bytes(checked(RESEARCH / "offer.json", OFFER_PIN))
    env = environment(root)
    env.update(TMPDIR=str(root / "tmp"), XDG_CACHE_HOME=str(root / "tmp"))
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=25)
    command = ["/usr/bin/timeout", "--kill-after=2s", "90s", python, "-IB", __file__, "child", root]
    binding["command"] = list(map(str, command))
    write(root / "binding.json", binding)
    clock = measure(command, env, root / "translated")
    write(root / "clock.json", clock)


def seal(root):
    from joint_publication import artifacts
    from raw_0016_best_score import position_sides
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification.paired_publication import evidence, verify_v3_publication

    binding, clock = read(root / "binding.json"), read(root / "clock.json")
    for name, pin in binding["source_sha256"].items():
        checked(HERE / name, pin)
    admission = binding["admission"]
    historical = json.loads(checked(PRIOR / "result-final.json", RAW_RESULT_PIN))["original"]["stock"]
    used = root / "translated"
    port = root / "saved-port.json"
    audit = read(port) if port.is_file() else {}
    result = dict(clock=clock, named_raw_containing=historical, audit=audit, named_detector=NATIVE,
                  binding_sha256=sha256((root / "binding.json").read_bytes()).hexdigest())
    known = historical["science"]
    frozen = evidence(PRIOR / "stock", known["receipt"], historical["process"]["clock"]["started_unix_ns"], read_only=True)
    verify_v3_publication(PRIOR / "stock", frozen["receipt"])
    pictures = artifacts(PRIOR / "stock", frozen["receipt"])
    if frozen != known or canonical_digest(pictures["images"]) != canonical_digest(historical["figures"]):
        raise ValueError("The raw containing control changed from its scored archive")
    if clock["exit_code"]:
        result.update(outcome="process_failure", terminals=[str(p) for p in used.glob("fast-scan-automatic-work/*/terminal.json")])
    else:
        if any(audit[k] != count for k, count in dict(startup=1, inventory_calls=1, handoffs=1, waveform_attempts=0).items()):
            raise ValueError("The stock publication failed its one saved handoff audit")
        receipt = json.loads((root / "translated.stdout").read_text().splitlines()[-1])
        verify_v3_publication(used, receipt)
        fresh = evidence(used, receipt, clock["started_unix_ns"], read_only=True)
        validate_packet(json.loads(checked(one(used, "detections.json"), NATIVE[7:])), binding)
        terminal = read(one(used, "terminal.json"))
        if (receipt["region"] != binding["offer"] or receipt["session_id"] != admission["session"]
                or terminal["native_sha256"] != NATIVE or fresh["raw_authority"] != known["raw_authority"]
                or receipt["window_count"] != known["receipt"]["window_count"] or receipt["counts"] != known["receipt"]["counts"]):
            raise ValueError("The translated result changed original detector identity or offer")
        media = artifacts(used, receipt)
        sides = None
        if receipt["decision"] == "complete":
            rows, = audit["selected_packets"]
            for arm, observations in rows.items():
                owners = {oid: satellite for oid, satellite, role in observations}
                if not observations or len(owners) != len(observations) or canonical_digest(owners) != fresh["owners"][arm]:
                    raise ValueError("Observed named roles and owners differ from the published owners")
            sides = position_sides(FastStandardAnalysisStore(used), receipt, media, expected_points=None)
        elif receipt["decision"] != "withheld" or not fresh["reason"] or media["images"] or any(
                arm["latlon"] is not None for arm in fresh["arms"].values()):
            raise ValueError("A withhold needs an explanation and absent positions and figures")
        result.update(outcome=receipt["decision"], science=fresh, terminal=terminal, media=media, sides=sides)
    write(root / "sealed.json", result)


def score(root):
    from triage_bounds import REFERENCE, REFERENCE_SHA256, distance_km

    path = root / "sealed.json"
    stock = read(path)
    binding = read(root / "binding.json")
    research = json.loads(checked(RESEARCH / "checked.json", RESEARCH_PIN))
    reference = json.loads(checked(REFERENCE, REFERENCE_SHA256))
    site, = [c for c in reference["cases"] if c["dataset_label"] == "DS30-0016"]
    if not site["authority_eligible"] or not site["sealed_metadata_digests_verified"]:
        raise ValueError("The physical evaluation reference lacks its original authority")
    truth = [site["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    distance = distance_km(truth, binding["offer"]["center"])
    if (distance < 2*binding["offer"]["width_km"] or research["offer"] != binding["offer"]
            or research["native_sha256"] == NATIVE or research["raw_authority"] != binding["admission"]["raw_authority"]):
        raise ValueError("Expected the same omitted offer and separate research signed receiver")

    def positions(arms):
        return {a: dict(arm, error_km=distance_km(truth, arm["latlon"]) if arm["latlon"] else None)
                for a, arm in arms.items()}

    write(root / "score.json", dict(distance_to_offer_center_km=distance, named_outcome=stock["outcome"],
        named_translated=positions(stock.get("science", {}).get("arms", {})), named_false_fix=stock["outcome"] == "complete",
        named_containing=positions(stock["named_raw_containing"]["science"]["arms"]),
        research_native_sha256=research["native_sha256"], research_receipt_sha256=RESEARCH_PIN,
        research={name: dict(outcome=run["science"]["decision"], false_fix=run["false_fix"], clock=run["clock"],
                            arms=positions(run["science"]["terminal"]["arms"])) for name, run in research["runs"].items()},
        sealed_sha256=sha256(path.read_bytes()).hexdigest(), reference_sha256=REFERENCE_SHA256))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "child", "seal", "score"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    {"launch": launch, "child": child, "seal": seal, "score": score}[args.action](args.root)
