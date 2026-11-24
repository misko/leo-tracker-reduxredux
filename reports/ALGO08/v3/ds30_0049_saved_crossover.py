"""Cross the two authentic generation-2 detector packets with both raw solvers."""

import argparse
from contextlib import contextmanager, ExitStack
from inspect import getsource
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

import integrated_original_batch as batch


STUDY = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
CASE = STUDY / "cases/DS30-0049"
ARCHIVE = Path("/srv/bulk/leo-dev/ds30-full-20261121/snapshot/inputs/DS30-0049/tle")
OFFER = STUDY / "offer.json"
BUILD = STUDY / "frozen-build/build.json"
BUILD_PIN = "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"
PAIR_PIN = "7514497ea681194487e8d85aecf2d739e996abf2b90566d446f81fe38875c36b"
AUTHORITY_PIN = "07bf604c34efdf057186a7e47b899a9c942b452f956efde454b1e7699046a1cc"
INPUT_PIN = "5d338f12159148772b9e5ec31521e55c7867e4fe7c6fd65f28594e69c0ae3b4e"
ROLES = ("installed", "successor")
ARMS = ("c0", "fitted_c")
MODE = {f"{solver}-{packet}": (solver, packet) for solver in ROLES for packet in ROLES}


def read(path):
    return json.loads(path.read_bytes())


def one(root, pattern):
    answer, = root.glob(pattern)
    return answer


def reject_waveforms(event, args):
    if event != "open" or not isinstance(args[0], (str, bytes)):
        return
    path = Path(os.path.abspath(os.fsdecode(args[0])))
    if (path.name.endswith(batch.WAVEFORM_SUFFIX) or path.is_relative_to(batch.QNAP)
            or path.is_relative_to(batch.BULK) and not path.is_relative_to(ARCHIVE)):
        raise ValueError(f"Saved crossover cannot open this original path: {path}")
    if path.is_relative_to(ARCHIVE) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_TRUNC | os.O_CREAT):
        raise ValueError(f"Original causal catalogue must remain read-only: {path}")


def bind_input():
    """Reopen only the sealed generation-2 metadata, stock inventory, and native."""
    from leo.contracts.digests import canonical_digest
    from empty_bootstrap import bind_native

    pair = batch.document(CASE / "pair.json", PAIR_PIN)
    source = batch.document(CASE / "input.json", INPUT_PIN)
    authority = batch.document(CASE / "authority.json", AUTHORITY_PIN)
    if (pair["generation"] != 2 or not pair["verified_pair"] or not pair["same_lease"]
            or pair["actual_order"] != list(ROLES)
            or source["archive"] != str(ARCHIVE)
            or source["authority"] != authority
            or pair["authority_sha256"] != batch.tagged(AUTHORITY_PIN)):
        raise ValueError("Expected the corrected, same-lease original DS30-0049 pair")
    batch.checked(OFFER, authority["region_sha256"])
    if batch.archive_digest(ARCHIVE, authority["causal_cutoff_utc_ns"]) != authority["archive_sha256"]:
        raise ValueError("The offered original causal archive changed")
    packets, inventories, originals = {}, {}, {}
    for role in ROLES:
        group = CASE / role / "attempt-000002"
        result = batch.document(group / "result.json", pair["attempt_result_sha256"][role])
        if result["outcome"] != "complete" or result["raw_identity"] != authority or result["grid_points"] != 179:
            raise ValueError(f"The original {role} diagonal lacks matched verified publication")
        folder = group / "publication"
        data = batch.checked(one(folder, "fast-scan-automatic-work/*/detections.json"), result["native_sha256"])
        native = json.loads(data)
        receipt = result["evidence"]["receipt"]
        terminal_path = folder / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json"
        terminal = batch.document(terminal_path, receipt["terminal_sha256"])
        inventory = batch.document(folder / "fast-scan-inputs" / (authority["session_id"] + ".json"),
                                   authority["inventory_sha256"])
        detector = native["provenance"]["detector_sha256"].removeprefix("sha256:")
        bind_native(native, authority["session_id"], authority["inventory_sha256"], detector,
                    expected=result["native_sha256"])
        batch.match_native(authority, native)
        if (inventory["window_count"] != authority["window_count"]
                or terminal["native_sha256"] != result["native_sha256"]
                or receipt["region"] != source["offered_region"] or terminal["region"] != source["offered_region"]
                or receipt["counts"]["processed"] != native["provenance"]["processed_windows"]
                or canonical_digest(inventory) != authority["inventory_sha256"]):
            raise ValueError(f"Raw {role} publication diverged from its source and region")
        packets[role], inventories[role], originals[role] = native, inventory, result
    if (inventories["installed"] != inventories["successor"]
            or packets["installed"]["delivery_clocks"] != packets["successor"]["delivery_clocks"]
            or packets["installed"]["clock_anchor"] != packets["successor"]["clock_anchor"]
            or originals["installed"]["native_sha256"] == originals["successor"]["native_sha256"]):
        raise ValueError("Same original inventory and clocks must identify two distinct signed packets")
    return authority, inventories["installed"], packets, originals, source["offered_region"]


def inventory_hook(authority, inventory):
    def stock_inventory(self, recording, *, verify_windows=True):
        if str(recording) != authority["recording"] or verify_windows:
            raise ValueError("The saved solver requested an unauthorized recording or raw inventory traversal")
        return authority["session_id"], authority["inventory_sha256"], inventory
    return stock_inventory


def allowed_scope(path, *, root=None):
    """Keep the exact archived TLE/portable ports on the enrolled path."""
    path = batch.direct(path)
    if root is not None and (not path.is_relative_to(root) or path.stat().st_dev != root.stat().st_dev):
        raise ValueError(f"Saved publication resource escaped its recorded root: {path}")
    return path


def admit_released_detector(original):
    """Remove the raw-only detector inequality for an already authenticated packet."""
    source = getsource(original)
    clause = 'or specification["detector_sha256"] == handoff.receiver'
    if source.count(clause) != 1:
        raise ValueError("The reviewed raw-only detector admission check changed")
    scope = dict(original.__globals__)
    exec(compile(source.replace(clause, "", 1), original.__code__.co_filename, "exec"), scope)
    return scope[original.__name__]


@contextmanager
def selected_rows(rows):
    from tools import algo08_position

    original = algo08_position.selected_packet

    def observed(*args, **options):
        packet = original(*args, **options)
        if rows:
            raise ValueError("Expected one original selected evidence packet")
        if packet is not None:
            rows.update({arm: [[r["observation_id"], r["norad"], r["role"]] for r in values]
                         for arm, values in packet["rows"].items()})
        return packet

    with patch.object(algo08_position, "selected_packet", observed):
        yield


def stock(publication, spec, args, handoff, authority, inventory):
    from leo.storage.fast_scan import FastScanStore
    from tools import algo08_scan

    rows = {}
    args.output.mkdir()
    request = SimpleNamespace(recording=args.recording, region=args.region,
                              archive=args.archive, bulk_root=args.output)
    with (patch.object(FastScanStore, "inventory", inventory_hook(authority, inventory)),
          handoff.install(algo08_scan), selected_rows(rows)):
        # The released lazy facade was installed by the checked bootstrap
        # before binding the saved handoff.
        receipt = publication.run(request, dict(spec, startup="stock"))
    return receipt, rows, {}


def charted(publication, spec, sources, args, handoff, authority, inventory, acceleration):
    import empty_bootstrap as boot
    import exact_named_raw as raw
    import integrated_original_entry as integrated
    from combined_successor_raw_entry import solver_ports
    from leo.analysis.glrt_frequency_input import frequency_evidence
    from leo.storage.fast_scan import FastScanStore
    from short_graph_guard import prove
    from unified_short_bootstrap import withhold

    # Reuse the actual raw successor's empty/graph checks after its held selector.
    # Crossed packets are already the complete released output of their receiver.
    started = perf_counter(), process_time()
    scan = boot.staged_scanner(sources)
    offer = scan.Algo08Region.parse(read(args.region))
    guard = boot.empty_reason(handoff.native, frequency_evidence)
    proof, ports, research = None, {}, None
    with TemporaryDirectory() as scratch, ExitStack() as stack:
        assets = Path(scratch)
        for name in (*scan.PINS, "native", "projector.so"):
            origin = Path(spec["detector"]) if name == "cancellation-factors.so" else boot.RELEASE / "assets" / name
            (assets / name).symlink_to(origin)
        scan.PINS["cancellation-factors.so"] = spec["detector_sha256"]
        for name, checksum in scan.PINS.items():
            boot.checked(assets / name, checksum)
        if guard is None:
            proof = prove(handoff.native, assets, use_time_support=True, use_curvature_extent=True)
            if proof["proven"]:
                guard = "no_active_curvature"
        stack.enter_context(patch.object(FastScanStore, "inventory", inventory_hook(authority, inventory)))
        if guard is None:
            # Only the normal raw admission inequality changes. The complete
            # publisher, history route, rank refusal, renderer, grid and
            # verification remain the source-checked charted implementation.
            stack.enter_context(patch.object(raw, "publish_active", admit_released_detector(raw.publish_active)))
            stack.enter_context(patch.object(raw, "staged_path", allowed_scope))
            stack.enter_context(integrated.positive_ports(solver_ports, acceleration, ports))
            extent = (proof or {}).get("curvature_extent", {})
            receipt, research = raw.publish_active(args, publication, spec, handoff, {},
                                                   no_active_curvature_sha256=extent.get("native_sha256"))
        else:
            boot.check_inert_solver_assets(assets)
            receipt = withhold(scan, args, offer, assets, handoff, guard, graph_proof=proof)
    rows = research["evidence"]["owner_rows"] if research is not None else {}
    return receipt, rows, dict(early_proof=proof, early_withhold=guard, successor_ports=ports,
                               saved_scientific_elapsed_s=perf_counter()-started[0],
                               saved_scientific_cpu_s=process_time()-started[1])


def worker(mode, output):
    import empty_bootstrap as boot

    if len(os.sched_getaffinity(0)) != 1 or output.exists() or not output.is_absolute():
        raise ValueError("Use one pinned CPU and a fresh local publication directory")
    for name in batch.THREADS:
        os.environ[name] = "1"
    _, spec, sources, publication, _ = boot.load_runtime()
    from unified_short_bootstrap import Handoff

    authority, inventory, packets, originals, offered = bind_input()
    solver, detector = MODE[mode]
    packet = packets[detector]
    handoff = Handoff(authority["session_id"], authority["inventory_sha256"],
                      packet["provenance"]["detector_sha256"][7:], packet)
    args = SimpleNamespace(output=output, recording=Path(authority["recording"]), archive=ARCHIVE, region=OFFER,
                           archive_sha256=authority["archive_sha256"], history_risk_route=True,
                           cairo_six_sheets=True, cairo_residual_layout=False)
    if solver == "installed":
        receipt, rows, audit = stock(publication, spec, args, handoff, authority, inventory)
    else:
        book, _, producer_cutoff = batch.load_build(BUILD, BUILD_PIN)
        if producer_cutoff >= authority["causal_cutoff_utc_ns"]:
            raise ValueError("Original successor diagonal required an independently earlier portable index")
        portable = book["native"]["--portable-orbit-index"]
        args.portable_orbit_index = Path(portable["path"])
        args.portable_orbit_index_sha256 = batch.tagged(portable["sha256"])
        args.portable_orbit_producer_sha256 = batch.tagged(book["portable_producer"]["sha256"])[7:]
        fast = book["native"]["--legacy-first-map-fast"]
        acceleration = batch.document(Path(fast["path"]), fast["sha256"])
        receipt, rows, audit = charted(publication, spec, sources, args, handoff, authority, inventory, acceleration)
    native = one(output, "fast-scan-automatic-work/*/detections.json")
    terminal = output / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json"
    submitted = originals[detector]["native_sha256"]
    batch.checked(native, submitted)
    observed = batch.document(terminal, receipt["terminal_sha256"])
    if (handoff.calls != 1 or receipt["region"] != offered or observed["region"] != offered
            or observed["native_sha256"] != submitted or receipt["session_id"] != authority["session_id"]
            or receipt["decision"] not in ("complete", "withheld")):
        raise ValueError("Saved solver changed the native handoff, original region, or published disposition")
    from aperture_trial import write

    write(output / "crossover-worker.json", dict(mode=mode, solver=solver, detector=detector,
          submitted_native_sha256=submitted, receipt=receipt, ordered_owners=rows, audit=audit,
          waveform_reads=0, verified_handoffs=handoff.calls))


def main():
    sys.addaudithook(reject_waveforms)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("probe", *MODE))
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    if args.mode == "probe":
        import empty_bootstrap as boot
        boot.load_runtime()
        authority, _, _, originals, _ = bind_input()
        batch.load_build(BUILD, BUILD_PIN)
        print(json.dumps(dict(session=authority["session_id"], both_raw_controls=sorted(originals), waveform_reads=0)))
    else:
        worker(args.mode, args.output)


if __name__ == "__main__":
    main()
