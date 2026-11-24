"""Read exact runner-up costs from one pre-finish frozen association."""

import argparse
from contextlib import contextmanager
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import resource
import sys
from time import perf_counter, process_time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
from prefix_transfer_0419 import checked, write


DENSE = Path("/tmp/leo-v3-0008-prefix-transfer-result05")
MEDIUM = Path("/dev/shm/leo-v3-nomination-handoff-0316-01")
ADMISSION = "f2a1b18b462ca78e3b5bda271ba2f733d3e3b0df303c6b0f099770dfa91ab2c4"
DENSE_JOB = "3898fd83a3404f4df9e50c8fa4a7ca9675d11a815cb08db912378577b8cf612e"
MEDIUM_BINDING = "a24730fe2c03a947bf92935c4d8a8e6df979fcd5b98905888ef7c64f5321fc7d"
FONT = "3ec97e620a1fa0115bbbdaefd3ddd47382fd0aed525281d7f1fc88a8614f282a"
CASES = ("dense", "medium")
PROTOCOL = HERE / "pre-finish-margin-protocol.md"
GAP = 2.


class EndOfStage(BaseException):
    pass


class UnsupportedStage(BaseException):
    """Prevent the numerical route from retrying at another scope."""


def clock(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def now():
    return process_time(), perf_counter()


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def parse(path, pin):
    return json.loads(checked(path, pin))


def ranked(cost, passing, visible):
    import numpy as np

    if cost.shape != passing.shape or visible.shape != cost.shape or np.any(~np.isfinite(cost[passing & visible])):
        raise UnsupportedStage("Unexpected finite original cost or eligibility layout")
    rows = np.flatnonzero(passing & visible)
    return rows[np.argsort(cost[rows], kind="stable")]


def inspect_association(scan, result, method):
    import numpy as np

    _, selected, nominations, bank = result
    f, elevation, _ = bank
    shape = (len(scan.norads),)
    readout, prices = [], dict(profile_cpu_s=0., profile_elapsed_s=0.)
    if len(selected) != len(scan.curved) or set(nominations) != set(scan.curved):
        raise UnsupportedStage("The original compact call did not visit every active curve")
    for i, accepted in zip(scan.curved, selected, strict=True):
        t, ix = scan.tracks[i], scan.index[i]
        witness = nominations[i]
        started = now()
        # These are the exact inputs and gate from installed ScanLikelihood.association.
        terms = scan.curve(i, witness["y"], t["rf_hz"] / 11.5e9 * f[:, ix], method)
        visible = elevation[:, ix].min(axis=1) >= 0
        paid = clock(started)
        prices["profile_cpu_s"] += paid["cpu_s"]
        prices["profile_elapsed_s"] += paid["elapsed_s"]
        costs, passing = terms["cost"], terms["passing"]
        keep = np.isfinite(witness["terms"]["cost"])
        if (costs.shape != shape or terms["alias"].shape != shape or keep.shape != shape
                or not np.array_equal(passing[keep], witness["terms"]["passing"][keep])):
            raise UnsupportedStage("The compared compact rows differ from the full profiler")
        order = ranked(costs, passing, visible)
        visible_choice = int(np.argmin(np.where(visible, costs, np.inf)))
        choice = int(order[0]) if len(order) else visible_choice
        if (choice != accepted["candidate_index"] or visible_choice != witness["j"]
                or bool(len(order)) != accepted["compatible"] or costs[choice] != accepted["cost"]
                or t["key"] != accepted["component"]):
            raise UnsupportedStage("The exact full scorer did not reproduce the original winner and gate")
        gap = float(costs[order[1]] - costs[order[0]]) if len(order) >= 2 else None
        readout.append(dict(curve=t["key"], observation_ids=t["observation_ids"], points=len(ix),
            finite_visible=int(np.count_nonzero(visible & np.isfinite(costs))), feasible=len(order),
            original_winner=int(scan.norads[choice]), compact_compatible=bool(len(order)),
            second_retained_by_original=bool(keep[order[1]]) if len(order) >= 2 else None,
            sealed_gated_ranks=[(int(scan.norads[j]), float(costs[j]), float(terms["alias"][j])) for j in order],
            gap=gap, exact_ties=int(np.count_nonzero(costs[order] == costs[choice])) if len(order) else 0))
    return readout, prices


@contextmanager
def stop_at_margin(observation):
    import catalogue_block_rank as block
    import cold_finalist_race as cold

    base_install = block.install

    def forbidden(*args, **kwargs):
        raise UnsupportedStage("The rank reached original cold optimization without the frozen readout")

    @contextmanager
    def install(scan, tables, counters, *, borrow=False):
        with base_install(scan, tables, counters, borrow=borrow):
            original = scan.association

            def capture(state, base, point, method, *, all_tracks=False):
                import numpy as np

                if method != "receiver_smooth":
                    return original(state, base, point, method, all_tracks=all_tracks)
                centre = scan.search_region.native_point(scan, (0, 0))
                if all_tracks or state["extra"] or not np.array_equal(point, centre):
                    raise UnsupportedStage("The first calibrated association differs from the frozen offer-centre stage")
                started = now()
                result = original(state, base, point, method, all_tracks=all_tracks)
                compact = clock(started)
                started = now()
                rows, times = inspect_association(scan, result, method)
                observation.update(point="operator centre", method=method, arms="cold candidate before calibration split",
                    bank_size=len(scan.norads), curves=rows, ordinary_association=compact,
                    full_profile_and_readout=clock(started) | times, original_block_counts=dict(counters))
                raise EndOfStage

            with patch.object(scan, "association", capture):
                yield

    with (patch.object(block, "install", install), patch.object(cold, "partial_fits", forbidden),
          patch.object(cold, "original_fits", forbidden)):
        yield


def enrolled(case):
    admitted = parse(DENSE/"admission.json", ADMISSION)
    if case == "dense":
        bound_job = parse(DENSE/"full-20/job.json", DENSE_JOB)
        return bound_job, admitted["source_pins"]
    bound = parse(MEDIUM/"binding.json", MEDIUM_BINDING)["input"]
    req = parse(Path(bound["request"]), bound["packets"][bound["request"]])
    return dict(binding=bound, original_archive=req["original_archive"]), admitted["source_pins"]


def worker(root, child_pin):
    from empty_bootstrap import checked as verify
    from history_risk_weak_physical import deny_original
    from nomination_handoff_0255_publication import worker as frozen
    from prefix_transfer_0008 import resident
    import exact_named_route as exact

    resource.setrlimit(resource.RLIMIT_CPU, (18, 18))
    sys.addaudithook(deny_original)
    beginning = now()
    admission = parse(root/"admission.json", child_pin)
    if admission["wrapper"] != digest(Path(__file__)) or admission["protocol"] != digest(PROTOCOL):
        raise ValueError("The frozen stage executable changed")
    observation = {}
    job = root/"job.json"
    verify(job, admission["job_sha256"])
    try:
        with (stop_at_margin(observation), patch.object(exact, "resident_path", resident),
              patch.object(exact, "exact_ports", partial(exact.exact_ports, resident=resident))):
            frozen(job, admission["job_sha256"], root/"routed")
    except EndOfStage:
        write(root/"stage.json", dict(observation, worker_stage=clock(beginning),
            case=admission["case"], protocol=admission["protocol"], wrapper=admission["wrapper"],
            complete_solver_calls=0, backing_reads=0, waveform_reads=0))
        return
    raise RuntimeError("The saved run returned without the bounded stop")


def launch(root):
    from aperture_trial import write as official_write
    from clean_saved_publication import load_job
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from exact_named_route import checked_catalogue
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from nomination_handoff_0255_publication import remediation_pins
    from prefix_transfer_0008 import resident
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident as cache

    machine = host()
    if resident(root.parent) != Path("/tmp") or root.exists():
        raise ValueError("Need a fresh direct /tmp result directory")
    root.mkdir(mode=0o700)
    for case in CASES:
        started = now()
        folder = root/case
        folder.mkdir()
        for sub in ("fonts", "tmp", "routed"):
            (folder/sub).mkdir()
        job, sources = enrolled(case)
        if sources != remediation_pins():
            raise ValueError("The original frozen solver source set changed")
        bound = job["binding"]
        req = parse(Path(bound["request"]), bound["packets"][bound["request"]])
        if "issued" not in req and "admitted" not in req:
            request = folder/"request.json"
            req = dict(req, issued=bound["issued"], admitted=bound["admitted"])
            official_write(request, req)
            bound = dict(bound, request=str(request), packets=bound["packets"] | {str(request): digest(request)})
            job = dict(job, binding=bound)
        _, refs = checked_catalogue(bound, req, TleArchiveReader, canonical_digest, resident=resident)
        resident_archive = cache([str(ref.path) for ref in refs])
        if resident_archive["members"] != len(refs):
            raise ValueError("The original local archive is unavailable")
        font = "fontlist-v3.11.0.json"
        (folder/"fonts"/font).write_bytes(checked(Path("/dev/shm/leo-v3-nomination-handoff-0419-local01/fonts")/font, FONT))
        path = folder/"job.json"
        official_write(path, job)
        with patch("exact_named_route.resident_path", resident):
            load_job(path, digest(path))
        official_write(folder/"routed/binding.json", dict(input=bound))
        command = ["/usr/bin/timeout", "--signal=KILL", "24s", str(RELEASE/"venv/bin/python"), "-IB", __file__,
                   "worker", str(folder)]
        official_write(folder/"admission.json", dict(case=case, source_pins=sources, protocol=digest(PROTOCOL),
                    job_sha256=digest(path), wrapper=digest(Path(__file__)), machine=machine, command=command,
                    archive=resident_archive, setup=clock(started), limits=dict(cpu_s=18, wall_s=24)))
        env = environment(folder) | {"TMPDIR": str(folder/"tmp"), "XDG_CACHE_HOME": str(folder/"tmp")}
        timing = measure(command + ["--pin", digest(folder/"admission.json")], env, folder/"candidate")
        official_write(folder/"clock.json", timing)
        seal = {k: digest(folder/k) for k in ("admission.json", "clock.json")}
        if timing["exit_code"] == 0:
            seal["stage.json"] = digest(folder/"stage.json")
        official_write(folder/"seal.json", seal)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("operation", choices=("launch", "worker"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--pin")
    opts = cli.parse_args()
    if opts.operation == "launch":
        launch(opts.root)
    else:
        worker(opts.root, opts.pin)
