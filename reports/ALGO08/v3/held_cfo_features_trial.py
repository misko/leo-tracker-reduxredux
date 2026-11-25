"""Verify and time only the added feature phase on two sealed RAM fixtures."""

import argparse
import errno
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import socket
import sys
from time import perf_counter, process_time

from leo.analysis.localization_v3.tracks import winning_observations
from leo.analysis.polynomial_tracklets import TrackConfig

from . import held_cfo_features as stage


HERE = Path(__file__).resolve().parent
PLAN = HERE/"measurements/held-short-cfo-shrink-prediction.json.gz"
PLAN_PIN = "3e8881c463ff66d0f936e4ac4cfbe9f2589f5543a6e4a776081cffa2473ae99d"
BASELINE_PIN = "f7c721cd320c0b002b999aff47a2b47b930a7143832e32bef7eb3bf593af11fc"
CONFIG = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/assets/tracks.json")
CONFIG_PIN = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
CASES = {
    "DS30-0019": (
        "/dev/shm/leo-v3-cfo-epoch-0019-saved01/native.json",
        "1acd2fcf8104fe990eaf40c82848e723de2da0c74f1ac1f29f59c659442d8d0d",
        "/dev/shm/leo-v3-held-shrink-0019-ram01/output/derived-native.json",
        "a84d61f24e47b9d4833311105dcff92e0e1c29041b04386b09147130998583a4",
    ),
    "DS30-0274": (
        "/dev/shm/leo-v3-held-shrink-0274-stage02/ordinary/derived-native.json",
        "e0dace78ca3e31c9329ead12eea3c62853de3a7c6c44dff3c70802764adf76b5",
        "/dev/shm/leo-v3-held-shrink-0274-stage02/half-blend/derived-native.json",
        "4c25d9b9a36ddea34f429a9b5e9473ed9ba35b98e936ed3691b925345daec473",
    ),
}


def checked_bytes(path, pin):
    body = path.read_bytes()
    if stage.tag(body) != "sha256:"+pin:
        raise ValueError(f"Saved fixture changed at {path}")
    return body


def canonical(value):
    return stage.tag(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode())


def clock(start):
    wall, cpu = start
    return dict(wall_s=perf_counter()-wall, cpu_s=process_time()-cpu)


def proof():
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        fields = left.split()
        mounts[fields[4]] = right.split()[0], fields[5].split(",")
    if (mounts[str(HERE)][0] != "tmpfs" or "ro" not in mounts[str(HERE)][1]
            or any(v[0] in {"xfs", "nfs", "nfs4", "cifs"} for v in mounts.values())):
        raise ValueError("Expected only the checked read-only program and approved runtime")
    for paths in CASES.values():
        for path in paths[::2]:
            if mounts[path][0] != "tmpfs" or "ro" not in mounts[path][1]:
                raise ValueError("Every sealed data operand must be read-only RAM")
    forbidden = ("/srv/bulk", "/mnt/qnap01", "/proc/1/root/srv/bulk", "/srv/postgres-nvme",
                 "/feature_trial/held_short_cfo_shrink.py")
    for path in forbidden:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
        except OSError as error:
            if error.errno not in (errno.ENOENT, errno.EPERM, errno.EACCES):
                raise
        else:
            os.close(descriptor)
            raise ValueError(f"Forbidden path opened inside capsule {path}")
    for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
        try:
            conn = socket.socket(family)
        except PermissionError as error:
            if error.errno != errno.EPERM:
                raise
        else:
            conn.close()
            raise ValueError("The worker could open an external endpoint")
    if any(name.startswith(("reports.", "tools.")) for name in sys.modules):
        raise ValueError("A field-readout dependency entered the feature capsule")
    return dict(mount_namespace=os.readlink("/proc/self/ns/mnt"), network_namespace=os.readlink("/proc/self/ns/net"),
                denied=list(forbidden), socket_denied=True, all_scientific_data_readonly_tmpfs=True,
                stage_imports_from=str(Path(stage.__file__)), numeric_library=sys.modules["numpy"].__version__,
                configuration_sha256=CONFIG_PIN, cpu=sorted(os.sched_getaffinity(0)), nice=os.nice(0))


def run(case):
    from gzip import decompress

    start = perf_counter(), process_time()
    config = TrackConfig(**json.loads(checked_bytes(CONFIG, CONFIG_PIN))["config"])
    original_path, original_pin, derived_path, derived_pin = CASES[case]
    native = json.loads(checked_bytes(Path(original_path), original_pin))
    native_identity_before = canonical(native)
    setup = clock(start)
    # The normal publisher already pays for this original extraction.
    baseline_start = perf_counter(), process_time()
    ordinary, metadata = winning_observations(native)
    baseline = clock(baseline_start)
    faults = getrusage(RUSAGE_SELF)
    start = perf_counter(), process_time()
    annotations = stage.derive(native, config)
    corrected = stage.apply_to_winners(native, ordinary, annotations)
    feature = clock(start)
    end = getrusage(RUSAGE_SELF)
    verify_start = perf_counter(), process_time()
    plan = json.loads(decompress(checked_bytes(PLAN, PLAN_PIN)))
    expected = plan["cases"][case]
    worker = json.loads(checked_bytes(Path(derived_path), derived_pin))
    historical_winners, _ = winning_observations(worker)
    if (plan["pins"]["archived_predictions"] != BASELINE_PIN or expected["native_sha256"] != "sha256:" + original_pin
            or annotations.edits != expected["eligible"] or annotations.forecasts != expected["forecasts"]
            or annotations.gates != expected["residual_gates"] or annotations.eligibility != expected["graph_forecast_eligibility"]
            or any(expected["graph"][k] != value for k, value in annotations.masked_graph.items())
            or corrected != historical_winners or canonical(native) != native_identity_before
            or metadata["detector_sha256"] != annotations.native_identity[-1]):
        raise ValueError("The real candidate stage changed a sealed prediction or the consumed scientific rows")
    verify = clock(verify_start)
    return dict(case=case, original_native_sha256=original_pin, previous_variant_sha256=derived_pin,
                approved_config_sha256=CONFIG_PIN, forecast_plan_sha256=PLAN_PIN, edits=len(annotations.edits),
                masked_graph=annotations.masked_graph, original_winners=len(ordinary),
                released_consumed_rows_sha256=canonical(corrected), evidence_unchanged=True,
                source_checks_and_decoding=setup, ordinary_winning_extraction=baseline, additional_feature=feature,
                independent_readback=verify, feature_minor_faults=end.ru_minflt-faults.ru_minflt,
                feature_major_faults=end.ru_majflt-faults.ru_majflt, feature_input_blocks=end.ru_inblock-faults.ru_inblock,
                feature_output_blocks=end.ru_oublock-faults.ru_oublock, maxrss_kib=end.ru_maxrss)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=(*CASES, "proof"))
    parser.add_argument("--isolated", action="store_true")
    args = parser.parse_args()
    def forbidden(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            from os import fsdecode

            path = Path(fsdecode(args[0]))
            if (path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01")
                    or path.name.endswith((".ci16.zst", ".tle", ".tle.gz"))):
                raise ValueError(f"Feature replay cannot open {path}")

    if args.isolated:
        evidence = proof()
        sys.addaudithook(forbidden)
        if args.case == "proof":
            result = evidence
        else:
            if evidence["cpu"] != [2] or evidence["nice"] != 15:
                raise ValueError("Timed child requires the authorized low-priority CPU2 slot")
            result = run(args.case) | {"isolation": evidence}
    else:
        if args.case == "proof":
            parser.error("Isolation proof requires the capsule")
        sys.addaudithook(forbidden)
        result = run(args.case)
    result["python_cpu_through_readback_s"] = process_time()
    print(json.dumps(result, indent=2, allow_nan=False))
