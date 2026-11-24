"""Observe paid alternatives without running either final decision arm."""

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch
from weakref import ref


HERE = Path(__file__).resolve().parent
ROOTS = {case: Path(f"/dev/shm/leo-exact-solver-{case}-result01") for case in ("0008", "0057")}
RANK_SHA = {"0008": "sha256:dd27253a64c196400a86ce06be196ae0604f5108a13a69ef98f7ccb2257d92c3",
            "0057": "sha256:8435f840b36df46909cb170cc27258e45fc83cf49c42322f8f2e6c3de1ad3be7"}
RECEIPT_SHA = {"0008": "f4750387b41c8247e6195a162a5653f11c2fd2281b23faa857cddbb1bc29255a",
               "0057": "621db1154873ac24ce68b2c0bdc128dc5a6bff2f67166cb78455ac06b2342eec"}


def request(case):
    from aperture_trial import archive_identity, read
    from empty_bootstrap import checked
    from local_future_cli_trial import native_packet
    from mixed_named_finish_0008 import assigned, PREVIOUS

    root = ROOTS[case]
    receipt = json.loads(checked(root/"result.json", RECEIPT_SHA[case]))
    if case == "0008":
        job = assigned()
    else:
        source = receipt["input"]
        packet = native_packet(root/"candidate")
        inventory, = (root/"candidate/fast-scan-inputs").glob("*.json")
        job = dict(recording=source["recording"], region=source["region"], offer_sha256=source["region_sha256"],
                   authority=source["raw_authority"], session=inventory.stem, inventory=source["input_manifest"],
                   archive=source["archive"], issued=2717, native=source["native"]["candidate"], packet=str(packet),
                   cutoff_utc_ns=source["clock_cutoff_utc_ns"], saved_inventory=str(inventory),
                   projection=str(PREVIOUS/"projection.so"), libraries={key: source[key] for key in (
                       "geographic_library", "regional_track_library", "frontier_block_library")})
    archive = Path(job["archive"]["root"]).resolve(strict=True)
    for key, pin in (("packet", job["native"]), ("saved_inventory", job["inventory"])):
        path = Path(job[key]).resolve(strict=True)
        if not path.is_relative_to(Path("/dev/shm")):
            raise ValueError("Saved input must live in tmpfs")
        checked(path, pin.removeprefix("sha256:"))
    if (not archive.is_relative_to(Path("/dev/shm"))
            or archive_identity(archive)["snapshots_sha256"] != job["archive"]["snapshots_sha256"]):
        raise ValueError("The actual signed staged archive changed")
    trace = read(root/"candidate/joint-research-receipt.json")["route_details"]
    timing = receipt["options"]["rank" if case == "0008" else "ranks"][0]["rank"]
    return job, dict(grouped_rank=timing, full_cold=trace["cold_clocks"], overlap=trace["cold"]["overlap"],
                     finalized_branches=trace["cold"]["completed"])


class ExactStates:
    def __init__(self):
        self.bases, self.states = {}, set()
        self.sequence = 0

    def repeated(self, state, base, point, method, all_tracks):
        identifiers = []
        for array in base:
            tag = id(array)
            existing = self.bases.get(tag)
            if existing is None or existing[0]() is not array:
                self.sequence += 1
                existing = self.bases[tag] = (ref(array), self.sequence)
            identifiers.append(existing[1])
        key = (tuple(identifiers), tuple(point), method, all_tracks,
               tuple((name, state[name].dtype.str, state[name].shape, state[name].tobytes())
                     for name in ("beta", "phases", "smooth")),
               tuple((i, a.dtype.str, a.shape, a.tobytes()) for i, a in sorted(state["extra"].items())))
        repeated = key in self.states
        self.states.add(key)
        return repeated


@contextmanager
def observe_cold(associations):
    import numpy as np
    import cold_track_row_entry as entry
    from cold_track_row_reuse import CentreRows

    installed, original_gather = entry.shared_association_rows, CentreRows.__call__

    @contextmanager
    def share(scan, tables, work, *, borrow=False):
        if borrow:
            raise ValueError("The original cached gather must remain active")
        with installed(scan, tables, work, borrow=False):
            operation, evaluate = scan.association, scan.curve
            pending, current, seen = [], [], ExactStates()

            def gather(port, track, indices, frequency, elevation):
                arrays = original_gather(port, track, indices, frequency, elevation)
                pending[:] = (track, *arrays)
                return arrays

            def curve(i, y, predicted, method):
                track, found, visible = pending
                if track is not scan.tracks[i] or found is not predicted:
                    raise ValueError("Alternative observer missed the exact released gather")
                begin = process_time_ns()
                terms = evaluate(i, y, predicted, method)
                paid = process_time_ns() - begin
                good = np.flatnonzero(terms["passing"] & visible)
                nominee = int(np.argmin(np.where(visible, terms["cost"], np.inf))) if visible.any() else None
                indices = [int(j) for j in good]
                alternatives = [(int(scan.norads[j]), int(terms["alias"][j])) for j in indices]
                choice = (None if nominee is None else (int(scan.norads[nominee]), int(terms["alias"][nominee])))
                current.append(dict(track=i, gated=alternatives, nominee=choice, profile_cpu_ns=paid))
                return terms

            def association(state, base, point, method, *, all_tracks=False):
                current.clear()
                duplicate = seen.repeated(state, base, point, method, all_tracks)
                result = operation(state, base, point, method, all_tracks=all_tracks)
                if not current:
                    raise ValueError("Expected live paid catalogue curve alternatives")
                associations.append(dict(method=method, exact_repeat=duplicate, curves=current.copy()))
                return result

            with (patch.object(CentreRows, "__call__", gather), patch.object(scan, "curve", curve),
                  patch.object(scan, "association", association)):
                yield

    with patch.object(entry, "shared_association_rows", share):
        yield


def summarize(tracks, associations):
    from conflict_components import topology

    gated, actual, paid = defaultdict(set), defaultdict(set), Counter()
    repeats = repeats_ns = 0
    for stage in associations:
        for row in stage["curves"]:
            key = str(row["track"])
            gated[key].update(row["gated"])
            labels = set(row["gated"])
            if row["nominee"] is not None:
                labels.add(row["nominee"])
            actual[key].update(labels)
            paid.update((key, *choice) for choice in labels)
            repeats += stage["exact_repeat"]
            repeats_ns += row["profile_cpu_ns"] if stage["exact_repeat"] else 0
    return dict(actual=topology(tracks, actual), gates=topology(tracks, gated), paid_associations=len(associations),
                curves=sum(len(op["curves"]) for op in associations), unique_choices=len(paid),
                choice_occurrences=paid.total(), repeated_labels=paid.total()-len(paid),
                tracks_with_multiple_aliases=sum(any(len({a for s, a in choices if s == satellite})>1
                    for satellite, _ in choices) for choices in actual.values()), repeated_exact_curves=repeats,
                repeat_profile_cpu_ns=repeats_ns,
                association_profile_cpu_ns=sum(row["profile_cpu_ns"] for op in associations for row in op["curves"]))


class StopBeforeFinalists(BaseException):
    pass


def worker(case, output):
    import cumulative_grid_projection as baseline
    import unified_short_bootstrap as unified
    from aperture_trial import write
    from conflict_components import exclusive_edges, joined_sizes

    binding = json.loads((output/"binding.json").read_bytes())
    job, clocks = binding["job"], binding["historical"]
    target = output/"rank"
    publish = unified.publish_active
    alternatives, graph, report = [], [], {}
    archive = Path(job["archive"]["root"]).resolve(strict=True)

    def observed(*args, **kwargs):
        import cold_finalist_race as race
        import joint_publication as joint
        from blind_joint_finish import digest
        from duplicate_graph_proposals import stable_finalization
        from leo.analysis import graph_tracklets
        from leo.application.localization_v3_engine import _json_value
        from leo.contracts.digests import canonical_digest
        from leo.operations.tle_archive import TleArchiveReader
        from tools.pipeline_eval.variants import v5_core

        finish, route, read_tle = graph_tracklets.finish_lane, joint.full_catalogue_route, TleArchiveReader.read
        removed = Counter()

        def only_staged(reader, snapshot):
            if reader.root.resolve(strict=True) != archive:
                raise ValueError("Read outside exact staged archive")
            return read_tle(reader, snapshot)

        def observe_lane(t, y, order, n, models, config, **options):
            supports = {i: model["indices"].tolist() for i, model in enumerate(models)}
            edges = exclusive_edges(supports)
            before = process_time_ns()
            fitted = finish(t, y, order, n, models, config, **options)
            graph.append(dict(lane=len(graph), models=len(models), conflict_edges=len(edges),
                              components=joined_sizes(supports, edges), finish_cpu_ns=process_time_ns()-before))
            return fitted

        def cold(_mode, prepared, region, bound):
            scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "previous")
            before = process_time_ns(), perf_counter_ns()
            nodes = v5_core.ranked_initial_nodes(scan)
            rank_clock = dict(cpu_ns=process_time_ns()-before[0], elapsed_ns=perf_counter_ns()-before[1])
            seal = canonical_digest(json.loads(json.dumps(nodes, default=_json_value, allow_nan=False)))
            if seal != RANK_SHA[case]:
                raise ValueError(f"Pre-finalist rank changed: {seal}")
            tracks = [dict(observation_ids=t["observation_ids"], receiver=t["receiver"], channel=t["channel"],
                           rf_hz=t["rf_hz"], start_s=t["start_s"], end_s=t["end_s"]) for t in scan.tracks]
            report.update(rank_sha256=seal, ranks=len(nodes), witness_rank_cpu=rank_clock, graph_duplicates=dict(removed),
                          summary=summarize(tracks, alternatives), graph_arbitrations=graph, tracks=tracks,
                          observed_associations=alternatives, historical=clocks, input=job, waveform_calls=0)
            raise StopBeforeFinalists

        def deny(*args, **kwargs):
            raise RuntimeError("The diagnostic must stop before the original fallback can fit a position")

        def guarded_route(_original, *args, **kwargs):
            return route(deny, *args, **kwargs)

        with (patch.object(TleArchiveReader, "read", only_staged), patch.object(race, "refine", cold),
              patch.object(joint, "full_catalogue_route", guarded_route),
              patch.object(graph_tracklets, "finish_lane", observe_lane), stable_finalization(removed), observe_cold(alternatives)):
            return publish(*args, **kwargs)

    try:
        with patch.object(unified, "publish_active", observed):
            baseline.worker(output/"job.json", "combined", target)
    except StopBeforeFinalists:
        if any(target.glob("fast-scan-automatic-work/*/terminal.json")):
            raise ValueError("The probe reached a position publication")
        write(output/"result.json", report | dict(case=case, code_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
        return
    raise ValueError("The paid pre-finalist rank was not reached")


def launch(case, output):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment

    machine = host()
    if output.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Require a fresh tmpfs output")
    job, clocks = request(case)
    output.mkdir()
    (output/"tmp").mkdir()
    write(output/"binding.json", dict(job=job, historical=clocks, machine=machine))
    write(output/"job.json", job)
    env = environment(output)
    env["TMPDIR"] = str(output/"tmp")
    subprocess.run([RELEASE/"venv/bin/python", "-IB", __file__, case, output, "--child"], env=env, check=True, timeout=45)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=tuple(ROOTS))
    parser.add_argument("output", type=Path)
    parser.add_argument("--child", action="store_true")
    options = parser.parse_args()
    (worker if options.child else launch)(options.case, options.output)
