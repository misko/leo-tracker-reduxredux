"""Time the private original-member worker and its fresh installed raw control."""

import argparse
from functools import partial
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from empty_bootstrap import BASELINE, RELEASE, checked


CASES = ("DS30-0016", "DS30-0107")
SAVED = Path("/dev/shm/leo-v3-alternate-original-members-0016-result01")
MEMBERS_PIN = "c2592a165e00974c6c8c372b08e36d1659ecddc7fb4e199f45c0199e119d3652"
SAVED_NATIVE_PIN = "84867f69162488d46893d8024c230a9f6ab271979b8d9aa1056921da178925f8"
SAVED_RESULT_PIN = "54daa18a1f82f2d5e9d5c218106cb9ef6356098828cfa813df7ae53dbafb64f3"
SAVED_SEAL_PIN = "f71e13284ae1c146e979bc09487815a46d42f3c2a66494ac28617a59522c43a5"


def read(path):
    return json.loads(path.read_bytes())


def sources():
    return {name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
        Path(__file__).name, "alternate_original_raw.py", "alternate-original-raw-protocol.md")}


def worker(root):
    from alternate_original_raw import preserve_stock_acquisition, scan_report
    from empty_bootstrap import load_runtime

    book = read(root / "admission.json")
    request = book["request"]
    recording, archive, offer = (Path(request["recording"]), Path(request["archive"]["root"]), Path(request["region"]))
    staged, local = Path(book["staged_recording"]), Path("/dev/shm")
    device = local.stat().st_dev
    if (book["sources"] != sources() or not recording.is_mount()
            or recording.stat().st_dev != device or staged.stat().st_dev != device
            or (recording.stat().st_ino != staged.stat().st_ino) or not os.statvfs(recording).f_flag & os.ST_RDONLY
            or any(path.resolve() != path or not path.is_relative_to(local) or path.stat().st_dev != device
                   for path in (archive, offer, staged))):
        raise ValueError("Require the original enrolled read-only tmpfs recording, offer and catalogue")
    checked(offer, request["offer_sha256"])
    prohibited = set()

    def scope(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.path.abspath(os.fsdecode(args[0])))
            if (path in prohibited or path.is_relative_to("/mnt/qnap01")
                    or path.is_relative_to("/srv/bulk") and not path.is_relative_to(recording)):
                raise ValueError(f"Prohibited acquisition or archive source {path}")

    sys.addaudithook(scope)
    _, spec, _, publication, _ = load_runtime()
    from aperture_trial import write
    from tools import algo08_position, algo08_scan

    expected = json.loads(checked(SAVED / "members.json", MEMBERS_PIN)) if book["case"] == CASES[0] else None
    measured, stage_clocks, owners = {}, {}, {}
    sampled = preserve_stock_acquisition(algo08_scan, request, expected, prohibited, measured)
    ordinary_packet = algo08_position.selected_packet

    def timed(operation, key):
        def observe(*args, **kwargs):
            cpu, wall = process_time(), perf_counter()
            try:
                return operation(*args, **kwargs)
            finally:
                stage_clocks[key] = dict(cpu_s=process_time() - cpu, elapsed_s=perf_counter() - wall)
        return observe

    def selected_packet(*args, **kwargs):
        packet = ordinary_packet(*args, **kwargs)
        owners.update({arm: [[r["observation_id"], r["norad"], r["role"]] for r in rows]
                       for arm, rows in packet["rows"].items()})
        if not packet["position_grid"]["complete"]:
            raise ValueError("The candidate standard position grid is incomplete")
        return packet

    output = root / "candidate"
    output.mkdir(mode=0o700)
    with (patch.object(algo08_scan, "acquire", timed(sampled, "acquire")),
          patch.object(algo08_scan, "scan_report", partial(scan_report, algo08_scan.scan_report)),
          patch.object(algo08_scan, "solve", timed(algo08_scan.solve, "solve")),
          patch.object(algo08_position, "selected_packet", selected_packet)):
        # load_runtime already enabled the installed lazy exports before importing the scanner.
        args = SimpleNamespace(recording=recording, archive=archive, region=offer, bulk_root=output)
        receipt = publication.run(args, dict(spec, startup="stock"))
    write(output / "member-receipt.json", dict(acquisition=measured, stage_clocks=stage_clocks,
                                                selected_rows=owners, receipt=receipt))
    print(json.dumps(receipt))


def launch(case, root):
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from aperture_trial import write
    from causal_body_publication_trial import measure
    from clean_saved_0169_trial import output_seal
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from stock_raw_repeat import read_resident_custody, sealed_control, stock_command
    from tools.pipeline_eval.qualification.paired_publication import verified_v3

    cpu, start = process_time(), perf_counter()
    baseline = sealed_control(case)["admission"]
    request = baseline["request"]
    machine = host()
    if (root.exists() or root.parent.resolve() != Path("/dev/shm") or machine != baseline["machine"]
            or verified_v3(BASELINE) != baseline["stock"]):
        raise ValueError("The enrolled low-priority worker or tmpfs destination changed")
    if case == CASES[0]:
        seal = json.loads(checked(SAVED / "prediction-seal.json", SAVED_SEAL_PIN))
        if seal["members.json"] != MEMBERS_PIN or seal["restricted-native.json"] != SAVED_NATIVE_PIN:
            raise ValueError("The frozen even-member saved comparison changed")
        checked(SAVED / "members.json", MEMBERS_PIN)
    else:
        earlier = read(root.parent / "leo-v3-alternate-original-raw-0016-result01/result.json")
        if earlier["case"] != CASES[0] or not earlier["qualified"]:
            raise ValueError("The fixing case did not qualify for withholding transfer")
    resident, catalogue, custody, offer = read_resident_custody(case, request, baseline)
    staged = Path(baseline["stage"]["stage"] if case == CASES[0] else baseline["stage"]) / Path(request["recording"]).name
    root.mkdir(mode=0o700)
    (root / "tmp").mkdir()
    shutil.copytree(offer.parent / "fonts", root / "fonts")
    prefix = ["/usr/bin/timeout", "--kill-after=2s", "40s"]
    commands = {"candidate": [*prefix, str(RELEASE / "venv/bin/python"), "-IB", str(Path(__file__).resolve()),
                              "worker", case, str(root)], "stock": [*prefix, *stock_command(baseline, root)]}
    write(root / "admission.json", dict(case=case, machine=machine, request=request, staged_recording=str(staged),
          source_custody=custody, orbital_residency=catalogue(), raw_residency=resident(), sources=sources(),
          commands=commands, setup=dict(cpu_s=process_time() - cpu, elapsed_s=perf_counter() - start)))
    env = environment_for(root)
    for mode, command in commands.items():
        raw_before = resident()
        if mode == "stock":
            (root / mode).mkdir(mode=0o700)
        clock = measure(command, env, root / mode)
        write(root / (mode + "-clock.json"), dict(clock=clock, cache_before=raw_before, cache_after=resident(),
                                                command=command, catalogue_after=catalogue()))
        if clock["exit_code"] and mode == "candidate":
            break
    write(root / "prediction-seal.json", output_seal(root))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker"))
    parser.add_argument("case", choices=CASES)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.action == "launch":
        launch(args.case, args.root)
    else:
        worker(args.root)
