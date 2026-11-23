"""Run the two waveform-to-graph selectors on one sealed saved offer."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time

from aperture_trial import RELEASE, archive_identity, machine, read, write
from blind_joint_trial import trial
from paid_graph import select
from sparse_consensus import paid_visits
from sparse_consensus_trial import CASES, bound_inputs


class SamePacket(Exception):
    pass


def prepare_paid(native, rows, clocks, identity, mode, *, select_paid=None):
    from leo.analysis.graph_tracklets import fit_lane
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.contracts.digests import canonical_digest

    config_blob = (RELEASE / "assets/tracks.json").read_bytes()
    config_sha = sha256(config_blob).hexdigest()
    if config_sha != "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a":
        raise ValueError("Installed track configuration differs")
    config = TrackConfig(**json.loads(config_blob)["config"])
    source = native["source"]
    start = process_time()
    if select_paid is None:
        paid = paid_visits(rows)
        picks, stats = select(rows, paid, source["sample_rate_hz"], config, fit_lane, mode == "graph")
        stats.update(paid_lanes=2 * len(paid), mask_sha256=canonical_digest(sorted(paid)),
                     paid_native_cpu_s=sum(t for r, t in zip(rows, clocks, strict=True) if r["visit_index"] in paid)/1e9)
    else:
        picks, stats = select_paid(rows, clocks)
    stats.update(selection_cpu_s=process_time() - start, lanes=len(rows), returned=sum(map(bool, picks)),
                 config_sha256=config_sha)
    probes = [dict(r, candidates=p) for r, p in zip(rows, picks, strict=True)]
    binding = canonical_digest(["cancellation", source["raw_recording_authority_digest"],
                                identity["ledger"]["detector_sha256"], probes])
    native = dict(native, source=dict(source, probes=probes, analysis_manifest_sha256=binding),
                  provenance=dict(native["provenance"], run_id="blind-compact-" + binding[7:39]))
    return native, config, stats


def prepared_packet(case, mode):
    from leo.contracts.digests import canonical_digest

    native, rows, _, clocks, archive, offer, identity = bound_inputs(case)
    native, config, stats = prepare_paid(native, rows, clocks, identity, mode)
    identity.update(mode=mode, selection=stats, native_sha256=canonical_digest(native))
    return native, archive, offer, identity, config, paid_visits(rows)


def run(case, mode, out, prior=None, *, observe=None, select_paid=None):
    staged = {}

    def load():
        from leo.contracts.digests import canonical_digest

        native, rows, _, clocks, archive, offer, identity = bound_inputs(case)
        native, config, stats = prepare_paid(native, rows, clocks, identity, mode, select_paid=select_paid)
        identity.update(mode=mode, selection=stats, native_sha256=canonical_digest(native))
        if observe is not None:
            observe(native, identity, config)
        staged.update(identity=identity, cpu=process_time(), elapsed=perf_counter())
        if prior:
            reference = read(prior)["identity"]
            keys = ("case", "archive", "source", "offer", "ledger", "native_sha256")
            if all(identity[k] == reference[k] for k in keys):
                raise SamePacket()
        return native, archive, offer, {}, identity

    try:
        trial(case, out, repair=True, signed_finish=True, load_saved_inputs=load)
    except SamePacket:
        original = read(prior)
        write(out, dict(identity=staged["identity"], machine=machine(), result=original["result"], charged=None,
                        reused_solver_sha256=sha256(prior.read_bytes()).hexdigest()))
    except ValueError as exc:
        if str(exc) != "cavity nomination failed: ValueError('nonempty observation mask matching full design required')":
            raise
        identity = staged["identity"]
        if archive_identity(Path(identity["archive"]["root"])) != identity["archive"]:
            raise ValueError("Causal archive changed") from exc
        write(out, dict(identity=identity, machine=machine(), result=dict(status="failed", reason=str(exc), arms={}),
                        charged=dict(cpu_s=process_time()-staged["cpu"], elapsed_s=perf_counter()-staged["elapsed"]),
                        clock_scope="prepared input to solver exception"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("mode", choices=("margin", "graph"))
    parser.add_argument("out", type=Path)
    parser.add_argument("--prior", type=Path)
    args = parser.parse_args()
    run(args.case, args.mode, args.out, args.prior)
