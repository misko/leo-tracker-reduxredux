"""Compare complete and paid-only factor ledgers with the same cold signed solver."""

import argparse
import json
from pathlib import Path
from time import perf_counter, process_time

from aperture_trial import BENCH, archive_identity, inputs, machine, write
from blind_joint_trial import trial
from sparse_consensus import buffered, paid_visits


CASES = ("DS30-0016", "south-containing", "south-far")
MODES = ("complete", "buffered")


def bound_inputs(case):
    from reports.ALGO08.v3.anchor_sky import sealed_inputs
    from anchor_orbit_census import saved_ledger

    physical = case == CASES[0]
    name = case if physical else "south"
    pair = BENCH / "integration-shared/pairs" / name / "pair.json"
    ledger = BENCH / f"ledger-{name}.json.gz"
    authority = (Path("/srv/bulk/leo-dev/ds30-full-20261121/snapshot/inputs") / name / "request.json"
                 if physical else BENCH / "exact-curved-lookahead-south-inside/pair.json")
    path, _, original_offer, reader, source = sealed_inputs(pair, ledger, authority)
    native = json.loads(path.read_bytes())
    rows, original, clocks, binding = saved_ledger(ledger, path)
    archive, offer = reader.root, original_offer.document()
    if not physical:
        _, archive, offer, _, current = inputs(case)
        if current["raw_authority"] != source["raw_authority"] or archive_identity(archive) != archive_identity(reader.root):
            raise ValueError("Southern offer belongs to another input")
    identity = dict(case=case, archive=archive_identity(archive), offer=offer, source=source, ledger=binding)
    return native, rows, original, clocks, archive, offer, identity


def load(case, mode):
    from anchor_orbit_census import selected
    from leo.contracts.digests import canonical_digest

    native, rows, original, clocks, archive, offer, identity = bound_inputs(case)
    paid = paid_visits(rows)
    start = process_time()
    sparse = buffered(rows, paid, native["source"]["sample_rate_hz"])
    select_cpu = process_time() - start
    causal = selected(rows, [r["candidates"] if r["visit_index"] in paid else [] for r in rows])
    paid_cpu = sum(t for r, t in zip(rows, clocks, strict=True) if r["visit_index"] in paid) / 1e9
    stats = dict(lanes=len(rows), paid_lanes=2 * len(paid), all_native_cpu_s=sum(clocks) / 1e9,
                 paid_native_cpu_s=paid_cpu, buffered_selection_cpu_s=select_cpu,
                 complete_selections=sum(map(bool, original)), paid_causal_selections=sum(map(bool, causal)),
                 buffered_selections=sum(map(bool, sparse)), mask_sha256=canonical_digest(sorted(paid)))
    if mode == "buffered":
        probes = [dict(r, candidates=c) for r, c in zip(rows, sparse, strict=True)]
        digest = canonical_digest(["cancellation", identity["source"]["raw_authority"],
                                   identity["ledger"]["detector_sha256"], probes])
        native = dict(native, source=dict(native["source"], probes=probes, analysis_manifest_sha256=digest),
                      provenance=dict(native["provenance"], run_id="blind-compact-" + digest[7:39]))
    identity.update(mode=mode, replay=stats, native_sha256=canonical_digest(native))
    return native, archive, offer, {}, identity


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    context = {}

    def prepare():
        prepared = load(args.case, args.mode)
        context.update(identity=prepared[-1], cpu=process_time(), wall=perf_counter())
        return prepared

    try:
        trial(args.case, args.output, repair=True, signed_finish=True, load_saved_inputs=prepare)
    except ValueError as exc:
        if str(exc) != "cavity nomination failed: ValueError('nonempty observation mask matching full design required')":
            raise
        identity = context["identity"]
        if archive_identity(Path(identity["archive"]["root"])) != identity["archive"]:
            raise ValueError("Archive changed during the failed fit") from exc
        write(args.output, dict(identity=identity, result=dict(status="failed", reason=str(exc), arms={}),
                                machine=machine(), charged=dict(cpu_s=process_time() - context["cpu"],
                                                                elapsed_s=perf_counter() - context["wall"]),
                                clock_scope="prepared input to solver exception"))
