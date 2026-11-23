"""Prospective matched current-solver publication on the signed DS30-0155 packet."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from unittest.mock import patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from prospective_0316_solver import ARMS, DETECTOR, LIBRARIES, ORDER, SOURCE_PINS, inspect, owner_delta, verify_sources, worker
from prospective_small_physical import checked


HERE = Path(__file__).resolve().parent
CASE = "DS30-0155"
BASE = "00b32f5876ad482060b3a24ce01aa1449318416a"
LOCAL = Path("/tmp/ds30-v2-stage-all-6cdbac") / CASE
CASE_BINDING = Path("/srv/bulk/leo-dev/ds30-full-20261121/bindings") / f"{CASE}.json"
PRIOR = (Path("/dev/shm/leo-v3-saved-0160-pair-01"), Path("/dev/shm/leo-held-anchor-selected-dense-01"))
PAIR_SHA = "e07989fd71164913cc4c4120f5aa45be3d79881d8d3c148b007d85043eba1b00"
BINDING_SHA = "896e41b63b620a1fdf40a0fd81122dc94c7a71407facb1a01845e972d020b15b"
INVENTORY_SHA = "2e52b6ce8091e0bd8c39a44d8d847c65402b487091a7102beb0b847b377ffbb6"
OFFER_SHA = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
ROSTER_SHA = "0bc940b1181b6fdb5f52ec1c5b768bfdbd6d2334e721fe8350cfc9ad3ca643c3"
ARCHIVE_SHA = "sha256:8ea284d7b0d6aab59dec80477ada3e1cbddb59c44714ebb103c047fa12de839e"
CUTOFF = 1794774843029840664
SETTINGS = dict(native_sha="d7f52f2ad771cd17dc3434548bb079e3cd1552b22f390949da6eef9993f4d0d3",
                windows=6773, admitted=6179, audit_name="saved-0155-worker.json")
PINS = SOURCE_PINS | {
    "unified_short_bootstrap.py": "89567f7c5ceaae7cff38268747c85aa8bc9d843638560dea0a6b78c88102560d",
    "joint_publication.py": "9df6978f279577f972460a6b752511df9bf4c511e74d072ce4ff23ebd39ac5f7",
    "direct_residual_entry.py": "41f7931578bad531c2be89041ec27c035ad94ecb9dc956d086517956b272c4ad",
    "direct_orbit_entry.py": "8f06cfe10cefbe0121cd14994f1cdea3bcbdee56af8aa455dcd30465a53e1a43",
}


def pinned(path, pin):
    return json.loads(checked(path, pin))


def enrollment():
    from tools.pipeline_eval.qualification.paired_publication import V3_IDENTITY

    members = [x["case"] for x in pinned(HERE/"development/stages.json", ROSTER_SHA)["stages"]["4"]["cases"]]
    pair = pinned(LOCAL / "pair.json", PAIR_SHA)
    old = pair["runs"]["candidate"]
    case = pinned(CASE_BINDING, BINDING_SHA)
    binding, receipt = case["case"], old["receipt"]
    relative = LOCAL / "candidate"
    terminal, = (relative / "fast-scan-automatic-work").glob("*/terminal.json")
    raw, = terminal.parent.parent.glob("*/detections.json")
    terminal_doc = pinned(terminal, receipt["terminal_sha256"])
    inventory = relative / "fast-scan-inputs" / f"{receipt['session_id']}.json"
    manifests = [[str(Path("/srv/bulk") / row["path"]), "sha256:"+row["sha256"]] for row in binding["recording"]["segments"]]
    if (members != ["DS30-0374", "DS30-0008", CASE, "DS30-0001"] or binding["id"] != CASE
            or pair["candidate_specification_digest"] != V3_IDENTITY["frozen_specification"]
            or pair["candidate_specification"]["detector_sha256"] != DETECTOR
            or case["orbit_cutoff_ns"] != CUTOFF or pair["archive"]["snapshots_sha256"] != ARCHIVE_SHA
            or receipt["decision"] != "complete" or receipt["window_count"] != SETTINGS["windows"]
            or receipt["counts"]["processed"] != SETTINGS["admitted"] or receipt["session_id"] != binding["session_id"]
            or old["raw_authority"] != binding["raw_authority"] or terminal_doc["native_sha256"] != "sha256:"+SETTINGS["native_sha"]
            or manifests != [[row["path"], row["sha256"]] for row in pair["cache_observation"]["manifests"]]):
        raise ValueError("Signed case metadata differs from the frozen original 20 ms prescription")
    return dict(case=CASE, prior_members=members, stale_original_root=pair["archive"], session=receipt["session_id"],
                raw_authority=old["raw_authority"], inventory="sha256:"+INVENTORY_SHA, manifests=manifests,
                recording=pair["recording"], native_input=str(raw), inventory_input=str(inventory),
                causal_cutoff_utc_ns=CUTOFF, original_pair_sha256=PAIR_SHA, offer_sha256=OFFER_SHA,
                native_sha256=SETTINGS["native_sha"], signed_case_sha256=BINDING_SHA), old


def archive_plan(wanted, available):
    """Resolve content from earlier tmpfs archives without reading original bulk payloads."""
    local = {}
    for item in available:
        local.setdefault((item.sha256, item.byte_size), item.path)
    plan = {}
    for item in wanted:
        found = local.get((item.sha256, item.byte_size))
        plan[item.path.name] = dict(source=str(found) if found is not None else None,
                                    bytes=item.byte_size, sha256=item.sha256, collected_utc_ns=item.collected_utc_ns)
    return plan


def preflight(request):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    def sources(root):
        return TleArchiveReader(root).list_snapshots("space-track")

    origin = Path(request["stale_original_root"]["root"])
    refs = sources(origin)
    if (canonical_digest({row.path.name: row.sha256 for row in refs}) != ARCHIVE_SHA
            or len(refs) != 52 or sum(row.byte_size for row in refs) != 92_934_518
            or any(row.collected_utc_ns > CUTOFF for row in refs)):
        raise ValueError("Original archive snapshot names, sizes or cutoff changed")
    plan = archive_plan(refs, [row for root in PRIOR for row in sources(root/"tle")])
    missing = [name for name,row in plan.items() if row["source"] is None]
    reuse = Counter(str(Path(row["source"]).parents[3]) for row in plan.values() if row["source"])
    return dict(admitted=not missing, files=plan, absent=missing, missing_bytes=sum(plan[name]["bytes"] for name in missing),
                staged_sources=dict(reuse), read_original_snapshot_bytes=0, waveform_calls=0)


def materialize(root, request, plan):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    archive = root / "tle"
    destination = archive / "archive/space-track"
    destination.mkdir(parents=True)
    for name, row in plan["files"].items():
        origin = Path(row["source"]).resolve(strict=True)
        if not any(origin.is_relative_to(parent) for parent in PRIOR):
            raise ValueError("Snapshot bytes must come from the existing tmpfs archive")
        data = checked(origin, row["sha256"])
        if len(data) != row["bytes"]:
            raise ValueError("The staged snapshot changed size")
        (destination / name).write_bytes(data)
    census = TleArchiveReader(archive).list_snapshots("space-track")
    if canonical_digest({row.path.name: row.sha256 for row in census}) != ARCHIVE_SHA:
        raise ValueError("Staging changed exact snapshot timestamps or contents")
    native, inventory, offer = root/"named-detections.json", root/"inventory.json", root/"operator-offer.json"
    native.write_bytes(checked(Path(request["native_input"]), request["native_sha256"]))
    inventory.write_bytes(checked(Path(request["inventory_input"]), INVENTORY_SHA))
    offer.write_bytes(checked(PRIOR[0] / "operator-offer.json", OFFER_SHA))
    libs = {}
    for name, (_, pin) in LIBRARIES.items():
        path = root / f"{name}.so"
        path.write_bytes(checked(PRIOR[0] / path.name, pin))
        libs[name] = str(path)
    request.update(native_file=str(native), offer_file=str(offer), staged_inventory=str(inventory),
                   local_libraries=libs, local_archive=dict(root=str(archive), snapshots_sha256=ARCHIVE_SHA,
                                                            bytes=sum(row.byte_size for row in census)))


def invoke(job, mode, output):
    import unified_short_bootstrap as entry

    original = entry.publish_active

    def configured(args, *values, **options):
        args.direct_residual_figures = True
        args.direct_orbit_figures = True
        return original(args, *values, **options)

    with patch.object(entry, "publish_active", configured):
        worker(job, mode, output, source_pins=PINS, inventory_file=job.parent/"inventory.json", **SETTINGS)


def run(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    verify_sources(checked, PINS)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Expected one fresh private tmpfs output")
    root.mkdir()
    (root / "tmp").mkdir()
    request, _ = enrollment()
    plan = preflight(request)
    write(root / "admission.json", dict(request=request, archive=plan, host=machine,
          io_pressure=Path("/proc/pressure/io").read_text(), source_sha256=PINS,
          protocol_sha256=sha256((HERE/"prospective-0155-solver-protocol.md").read_bytes()).hexdigest()))
    if not plan["admitted"]:
        return
    start_cpu, start_wall = process_time(), perf_counter()
    materialize(root, request, plan)
    write(root / "stage-clock.json", dict(cpu_s=process_time()-start_cpu, elapsed_s=perf_counter()-start_wall))
    job = root / "request.json"
    write(job, request)
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=20)
    for mode in ORDER:
        output = root / mode
        command = [python, "-IB", __file__, "worker", job, mode, output]
        clock = measure(command, env, output)
        write(root / f"{mode}-clock.json", dict(timing=clock, command=list(map(str, command))))
        if clock["exit_code"]:
            raise RuntimeError(f"The saved {mode} process exit was sealed before validation")


def orbit_legends(directory, run):
    """Independently check each native orbit footer against fitted owner labels."""
    from io import BytesIO
    import math
    import numpy as np
    from matplotlib import colormaps
    from PIL import Image
    from direct_orbit_figures import GRAY, geometry, legend, legend_columns, library, surface
    from direct_orbit_figures_trial import NAMES
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    layout = run["worker"]["layout"]["work"]
    if layout.get("native_orbit_figures") != 4:
        return dict(native=False, fallback=layout.get("native_orbit_fallback"))
    labels = sorted({str(row[1]) for row in run["selected_rows"]["fitted_c"]})
    palette = colormaps["turbo"]
    entries = [("Unassociated", GRAY), *((sat, palette((i+.5)/len(labels))[:3]) for i,sat in enumerate(labels))]
    rows = math.ceil(len(entries)/6)
    height, _ = geometry(dict(rows=[None]*8, legend_rows=rows))
    last = height*.975 - 24
    footer = slice(int(last - (rows-1)*22 - 26), int(last + 12))
    c = library()
    with surface(c, height) as (canvas, surface_id, data):
        canvas.ink(1., 1., 1.)
        c.cairo_paint(canvas.ctx)
        legend(canvas, entries, height)
        c.cairo_surface_flush(surface_id)
        expected = data[footer, :, 2::-1].copy()
        columns = list(legend_columns(entries, canvas.text_width))
        separation = [x1-x0 - 46 - max(canvas.text_width(entries[i][0], 8) for i in group)
                      for (x0, group), (x1, _) in zip(columns, columns[1:])]
    if min(separation, default=20.) < 20.:
        raise ValueError("Independent orbit legend width exceeds the reviewed layout")
    store = FastStandardAnalysisStore(directory)
    run_id = run["worker"]["receipt"]["run_id"]
    for name in NAMES:
        value = store.artifact(run_id, name, run["figures"][name]["sha256"])
        with Image.open(BytesIO(value)) as pixels:
            if pixels.height != height or not np.array_equal(np.asarray(pixels.convert("RGB"))[footer], expected):
                raise ValueError(f"Independent fitted-owner legend differs in the published {name}")
    return dict(native=True, checked=list(NAMES), independent_fitted_ids=labels, width_gap_px=min(separation, default=None))


def evaluate(root, output):
    from aperture_trial import read, write
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    request, admission = (read(root / name) for name in ("request.json", "admission.json"))
    controls = pinned(LOCAL / "pair.json", PAIR_SHA)["runs"]["candidate"]
    actual = {}
    for mode in ORDER:
        destination = root / mode
        clock = read(root / f"{mode}-clock.json")["timing"]
        row = read(destination / SETTINGS["audit_name"])
        if clock["exit_code"]:
            raise ValueError("An archived process failed before the study was complete")
        actual[mode] = inspect(destination, mode, row["receipt"], clock, request, **SETTINGS)
    stock, cumulative = (actual[mode] for mode in ORDER)
    if any(stock["science"][key] != controls[key] for key in ("arms", "owners", "reason", "raw_authority", "scientific_digests", "artifacts")):
        raise ValueError("Fresh named v3 scientific and artifact evidence does not match the historical signed control")
    if not cumulative["worker"]["graph"].get("enabled"):
        raise ValueError("The cumulative exact Graph path was not enabled")
    legends = orbit_legends(root/"cumulative", cumulative) if cumulative["science"]["receipt"]["decision"] == "complete" else None
    reference, = (row["reference"] for row in pinned(REFERENCE, REFERENCE_SHA256)["cases"] if row["dataset_label"] == CASE
                  and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    truth = [reference[key] for key in ("latitude_deg", "longitude_deg")]
    scores = {mode: {arm: dict(horizontal_error_km=distance_km(truth, v["latlon"]) if v["latlon"] else None,
                               rf_rms_hz=v.get("rf_rms_hz")) for arm,v in result["terminal"]["arms"].items()}
              for mode,result in actual.items()}
    owners = {arm: owner_delta(stock["selected_rows"][arm], cumulative["selected_rows"].get(arm, [])) for arm in ARMS}
    figures = {name: {key: ours[key] == cumulative["figures"].get(name, {}).get(key) for key in ("size", "sha256", "rgba_sha256")}
               for name,ours in stock["figures"].items()}
    write(output, dict(case=CASE, base=BASE, order=ORDER, input_staged=True, waveform_calls=0,
                       inputs=request, admission=admission, stage_clock=read(root/"stage-clock.json"), scores=scores,
                       runs=actual, owners=owners, cairo_legends=legends, pair_figure_equality=figures,
                       named_reproduces_historical=True, reference_sha256=REFERENCE_SHA256))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    actions = cli.add_subparsers(dest="action", required=True)
    actions.add_parser("run").add_argument("root", type=Path)
    audit = actions.add_parser("evaluate")
    audit.add_argument("root", type=Path)
    audit.add_argument("output", type=Path)
    child = actions.add_parser("worker")
    child.add_argument("job", type=Path)
    child.add_argument("mode", choices=ORDER)
    child.add_argument("output", type=Path)
    args = cli.parse_args()
    if args.action == "run":
        run(args.root)
    elif args.action == "evaluate":
        evaluate(args.root, args.output)
    else:
        invoke(args.job, args.mode, args.output)
