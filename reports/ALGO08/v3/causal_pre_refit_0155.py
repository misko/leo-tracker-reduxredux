"""Measure one complete stock versus causal warm predictive publication on DS30-0155."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from causal_linear_refit import ARMS, elapsed, linear_policy, now
from prospective_0155_solver import ARCHIVE_SHA, CUTOFF, INVENTORY_SHA, OFFER_SHA, SETTINGS, pinned
from prospective_0316_solver import denied, owner_delta, saved_inventory
from prospective_small_physical import checked


HERE = Path(__file__).resolve().parent
STAGE = Path("/dev/shm/leo-v3-saved-0155-pair-01")
PRIOR = STAGE.with_name("leo-v3-saved-0155-result.json")
PRIOR_SHA = "63efc82d3c0fa0889f3c85e630ddb427f041b6174a7c9f175676c1f0fec64d75"
REQUEST_SHA = "c0533ae6b92b66593d59a2f9a7aaf2b64194563c18ef8038ec2afdfc66c1da79"
ORDER = ("control", "warm")
PROTOCOL = HERE / "causal-pre-refit-0155-protocol.md"
SOURCE_PINS = {
    "exact_graph_execution.py": "cee1c8e095f139d4e1b839dc84a3c25b96794a96031df05a16f7f876a67391fe",
    "exact_phase_forecast.py": "62229f0d6097252f2637aade83ea0dd2014308e9578e4513503a91b27e597b4b",
    "unified_short_bootstrap.py": "89567f7c5ceaae7cff38268747c85aa8bc9d843638560dea0a6b78c88102560d",
    "direct_orbit_entry.py": "8f06cfe10cefbe0121cd14994f1cdea3bcbdee56af8aa455dcd30465a53e1a43",
    "direct_residual_entry.py": "41f7931578bad531c2be89041ec27c035ad94ecb9dc956d086517956b272c4ad",
    "blind_joint_finish.py": "7d8d5a65ceb0e11150e28d0dbbddeabb7741ef1408ded6272500e4f0e012c708",
}


def request():
    from aperture_trial import archive_identity

    row = pinned(STAGE/"request.json", REQUEST_SHA)
    native, inventory, offer, archive = (Path(path) for path in (row["native_file"], row["staged_inventory"],
                                                                row["offer_file"], row["local_archive"]["root"]))
    paths = (native, inventory, offer, archive)
    if (any(not path.resolve(strict=True).is_relative_to(STAGE) for path in paths)
            or archive_identity(archive)["snapshots_sha256"] != ARCHIVE_SHA
            or row["inventory"] != "sha256:"+INVENTORY_SHA or row["causal_cutoff_utc_ns"] != CUTOFF):
        raise ValueError("The original signed named input must already exist in tmpfs")
    for path, pin in ((native, SETTINGS["native_sha"]), (inventory, INVENTORY_SHA), (offer, OFFER_SHA)):
        checked(path, pin)
    return row


def worker(mode, output):
    from named_weak_exact import run as publish

    row = pinned(STAGE/"request.json", REQUEST_SHA)
    output.mkdir()
    trace, media = [], {}

    @contextmanager
    def active():
        from leo.storage.fast_scan import FastScanStore, FastSegmentSource
        from leo.storage.short_window import ShortWindowReader
        from tools import algo08_position

        selected = algo08_position.selected_packet

        def capture(prepared, signed, fit):
            result = selected(prepared, signed, fit)
            media.update(owners={arm: [[v["observation_id"], v["norad"], v["role"]] for v in result["rows"][arm]] for arm in ARMS},
                         cavity_offered=fit is not None, cavity_adopted=bool(fit and fit["accepted"]),
                         signed_phase_adopted=bool(signed["signed"]["accepted"]))
            return result

        with (patch.object(FastScanStore, "inventory", saved_inventory(row, Path(row["staged_inventory"]))),
              patch.object(FastSegmentSource, "windows", denied), patch.object(ShortWindowReader, "windows", denied),
              patch.object(algo08_position, "selected_packet", capture), linear_policy(mode=="warm", trace)):
            yield

    args = SimpleNamespace(recording=Path(row["recording"]), archive=Path(row["local_archive"]["root"]),
                           region=Path(row["offer_file"]), bulk_root=output)
    begin = now()
    publish(args, optimized=True, saved=Path(row["native_file"]), expected="sha256:"+SETTINGS["native_sha"], analysis_scope=active)
    from aperture_trial import write

    write(output/"causal-pre-refit.json", dict(mode=mode, no_waveform=True, clock=elapsed(begin), pre_fit=trace, selected=media))


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use one fresh private tmpfs pair")
    for f, pin in SOURCE_PINS.items():
        checked(HERE/f, pin)
    req = request()
    root.mkdir()
    (root/"tmp").mkdir()
    source_pins = SOURCE_PINS | {name:sha256((HERE/name).read_bytes()).hexdigest() for name in
                                (Path(__file__).name, "causal_linear_refit.py", "named_weak_exact.py")}
    write(root/"binding.json", dict(request=req, historical_comparator_sha256=PRIOR_SHA, machine=machine,
                                     source_sha256=source_pins, protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest()))
    env = environment(root)
    env["TMPDIR"] = str(root/"tmp")
    exe = RELEASE/"venv/bin/python"
    subprocess.run([exe,"-Bc","from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=20)
    for mode in ORDER:
        destination = root/mode
        command = [exe,"-IB",__file__,"worker",mode,destination]
        row = measure(command, env, destination)
        write(root/f"{mode}-clock.json",dict(timing=row, command=list(map(str,command))))
        if row["exit_code"]:
            raise RuntimeError("The original child process clock and logs were retained")


def compare_grid(before, after):
    def points(grid):
        return {(r["east_km"],r["north_km"]):r["scores"] for r in grid["points"]}

    old, new = points(before), points(after)
    if len(old) != before["evaluated_points"] or len(new) != after["evaluated_points"]:
        raise ValueError("A standard grid contains duplicate points or missing scored coordinates")
    shared = old.keys() & new.keys()
    differences = {}
    for arm in ARMS:
        values = [abs(old[xy][arm]-new[xy][arm]) for xy in shared if arm in old[xy] and arm in new[xy]]
        differences[arm] = dict(common_numeric=len(values), max_abs_score_delta=max(values, default=None),
                                changed_scores=sum(v!=0. for v in values))
    return dict(shared_coordinates=len(shared), unique_coordinates={"control":len(old)-len(shared),"warm":len(new)-len(shared)},
                calibration=differences)


def audit_run(root, mode, request_row):
    from aperture_trial import read
    from joint_publication import artifacts
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0155_solver import orbit_legends
    from tools.pipeline_eval.qualification.paired_publication import evidence

    clock = read(root/f"{mode}-clock.json")["timing"]
    directory = root/mode
    named, scoped = (read(directory/f) for f in ("named-weak-exact.json","causal-pre-refit.json"))
    receipt = named["publication"]
    scientific = evidence(directory, receipt, clock["started_unix_ns"], read_only=True)
    workspace = FastScanStore(directory).automatic_workspace(receipt["run_id"], create=False)
    terminal = read(workspace/"terminal.json")
    native, = workspace.parent.glob("*/detections.json")
    checked(native, SETTINGS["native_sha"])
    if (clock["exit_code"] or named["acquisition"]["mode"] != "saved" or not scoped["no_waveform"]
            or scientific["raw_authority"] != request_row["raw_authority"] or receipt["session_id"] != request_row["session"]
            or terminal["native_sha256"] != "sha256:"+SETTINGS["native_sha"] or receipt["window_count"] != SETTINGS["windows"]
            or receipt["counts"]["processed"] != SETTINGS["admitted"] or not named["graph"]["enabled"]):
        raise ValueError("Saved named publication changed its original input or expected exact preparation")
    figs = artifacts(directory, receipt)["images"]
    info = dict(clock=clock,named=named,scope=scoped,science=scientific,terminal=terminal,figures=figs)
    if receipt["decision"] == "complete":
        store = FastStandardAnalysisStore(directory)
        grid, path = store.position_grid(receipt["run_id"]), store.position_path(receipt["run_id"])
        if (len(figs) != 8 or grid["evaluated_points"] != 179 or not grid["complete"]
                or any(doc["binding"]["position_png_sha256"] != figs["position"]["sha256"] for doc in (grid,path))):
            raise ValueError("Each complete saved fix must publish its own bound path, grid and eight checked images")
        owners = scoped["selected"]["owners"]
        info.update(grid=grid,path=path,cairo=orbit_legends(directory, dict(selected_rows=owners,figures=figs,
                          worker=dict(layout=named["rendering"],receipt=receipt))))
    elif figs or not terminal["reason"] or any(t["latlon"] is not None for t in terminal["arms"].values()):
        raise ValueError("An actual withheld publication must preserve its reason and omit figure/position claims")
    return info


def evaluate(root, output):
    from aperture_trial import read, write
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    binding = read(root/"binding.json")
    actual = {m:audit_run(root,m,binding["request"]) for m in ORDER}
    old = pinned(PRIOR, PRIOR_SHA)["runs"]["stock"]
    control, warm = (actual[m] for m in ORDER)
    control_exact = {k:control["science"][k]==old["science"][k] for k in ("arms","owners","scientific_digests","reason","raw_authority")}
    control_exact["ordered_owners"] = control["scope"]["selected"].get("owners") == old["selected_rows"]
    a,b = (r["scope"]["selected"].get("owners", {}) for r in (control,warm))
    owners = {arm:owner_delta(a.get(arm, []), b.get(arm, [])) for arm in ARMS}
    pair_same_science = {k:control["science"][k]==warm["science"][k] for k in ("arms","owners","scientific_digests","reason","raw_authority")}
    positions = {m:{arm:s["latlon"] for arm,s in d["terminal"]["arms"].items()} for m,d in actual.items()}
    truth, = (row["reference"] for row in pinned(REFERENCE,REFERENCE_SHA256)["cases"] if row["dataset_label"]=="DS30-0155"
               and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    ref = [truth[key] for key in ("latitude_deg","longitude_deg")]
    shifts = {arm:distance_km(positions["control"][arm],positions["warm"][arm])
              if all(p[arm] is not None for p in positions.values()) else None for arm in ARMS}
    errors = {mode:{arm:distance_km(ref, ll) if ll else None for arm,ll in p.items()} for mode,p in positions.items()}
    figs_same = {name:{k:value[k]==warm["figures"].get(name,{}).get(k) for k in ("sha256","rgba_sha256","size")}
                 for name,value in control["figures"].items()}
    grid = compare_grid(control["grid"], warm["grid"]) if "grid" in control and "grid" in warm else None
    write(output,dict(case="DS30-0155",binding=binding,reference_sha256=REFERENCE_SHA256,historical_stock_clock=old["process"],
          control_matches_historical_science=control_exact,matched_pair_science=pair_same_science,owners=owners,figures_match=figs_same,
          endpoint_shifts_km=shifts,local_20m_endpoint_screen=all(v is not None and v<=.020 for v in shifts.values()),
          horizontal_errors_km=errors,common_grid=grid,arms=actual))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="command",required=True)
    sub.add_parser("launch").add_argument("root",type=Path)
    examine = sub.add_parser("evaluate")
    examine.add_argument("root",type=Path)
    examine.add_argument("output",type=Path)
    job = sub.add_parser("worker")
    job.add_argument("mode",choices=ORDER)
    job.add_argument("output",type=Path)
    args = cli.parse_args()
    if args.command == "launch":
        launch(args.root)
    elif args.command == "evaluate":
        evaluate(args.root,args.output)
    else:
        worker(args.mode,args.output)
