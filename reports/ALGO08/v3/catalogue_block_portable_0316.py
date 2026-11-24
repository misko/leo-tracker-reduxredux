"""Measure one corrected portable acquisition input with grouped exact cold rank."""

import argparse
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
REPAIRED = Path("/dev/shm/leo-v3-portable-0316-regional-repair01/result.json")
REPAIRED_SHA = "6d764b657af37065af1789fead0390af621628372900d5845b63ef37c2dc95e2"
PORT_SOURCE = "e9392864c1a46d8fbe713cc2aa5612c358f701ef"
RANK_SHA = "sha256:107ae9362f1e628bb0f03f647e607307121f7354a362d951982ef31b8418e76a"
PINS = {
    "catalogue_block_port.py": "58822bc2ac42266d4677674bdeeef6e2eb4ee059992ea8ec9c29ffd18c2fd021",
    "catalogue_block_rank.py": "961bce0676c4cf55da4e72a417f0120aba398d48c4389b905aa3655f0d0f3311",
    "catalogue_block_bound.py": "757ddbd34b1c933d062d7e1613c5f039c6bb18bf13914b6d09ab51d2578fbe33",
}


def verified_port():
    from empty_bootstrap import checked

    for file, pin in PINS.items():
        checked(HERE/file, pin)


@contextmanager
def inclusive_rank(audit):
    import cold_finalist_race as race
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest
    from portable_orbit_index_trial import begin, timing
    from tools.pipeline_eval.variants import v5_core

    original = race.refine

    def refine(*args, **kwargs):
        ranked = v5_core.ranked_initial_nodes

        def measure(scan):
            start = begin()
            nodes = ranked(scan)
            clock = timing(start)
            start = begin()
            values = json.loads(json.dumps(nodes, default=_json_value, allow_nan=False))
            digest = canonical_digest(values)
            audit.append(dict(rank=clock, node_serialization=timing(start), nodes=len(nodes), digest=digest))
            return nodes

        with patch.object(v5_core, "ranked_initial_nodes", measure):
            return original(*args, **kwargs)

    with patch.object(race, "refine", refine):
        yield


def worker(root):
    import empty_bootstrap as release
    import portable_orbit_0316_repair as repair

    verified_port()
    startup, audit, scopes = release.load_runtime, [], []
    with ExitStack() as work:
        def loaded():
            environment = startup()
            from catalogue_block_port import use_catalogue_blocks

            scopes.append(work.enter_context(use_catalogue_blocks()))
            work.enter_context(inclusive_rank(audit))
            return environment

        work.enter_context(patch.object(release, "load_runtime", loaded))
        repair.worker(root)
    from aperture_trial import write

    counts, = scopes
    write(root/"rank.json", dict(port_commit=PORT_SOURCE, source_sha256=PINS, work=dict(counts), evaluations=audit))


def exact_rank(receipt):
    counters, = receipt["evaluations"]
    work = receipt["work"]
    if (receipt["port_commit"] != PORT_SOURCE or receipt["source_sha256"] != PINS
            or work.get("admitted_ranks") != 1 or work.get("original_ranks") != 0 or work.get("full_fallback", 0)
            or work.get("calls") != 624 or work.get("compact_calls") != 624 or work.get("rows_saved") != 892716
            or work["original_rows"] != work["rows_saved"]+work["rows_retained"]
            or counters["digest"] != RANK_SHA):
        raise ValueError("The combined run did not exercise the original exact full-catalogue rank")
    return counters


def compare(root):
    from aperture_trial import read, write
    from empty_bootstrap import checked
    from portable_orbit_0316_repair import without_timers

    digest = sha256(Path(__file__).read_bytes()).hexdigest()
    combined = read(root/"result.json")
    solo = json.loads(checked(REPAIRED, REPAIRED_SHA))
    rank = read(root/"rank.json")
    checked_rank = exact_rank(rank)
    actual, prior = (item["portable"] for item in (combined, solo))
    if (combined["scientific"] != solo["scientific"] or combined["artifact_sha256"] != solo["artifact_sha256"]
            or actual["preparation"]["fingerprint"] != prior["preparation"]["fingerprint"]
            or combined["native_validations"] != solo["native_validations"]
            or without_timers(actual["early_regional"]) != without_timers(prior["early_regional"])
            or actual["solve"]["orbit_policy"] != prior["solve"]["orbit_policy"]
            or actual["solve"]["cold_track_rows"]["ordinary_ranks"] != 0
            or actual["solve"]["cold_track_rows"]["shared_ranks"] != 1):
        raise ValueError("The grouped rank changed the repaired portable publication or its native work")
    write(root/"combined.json", dict(ordinary=combined["ordinary"], portable_only=prior, combined=actual,
          rank=rank, rank_validated=checked_rank, scientific=combined["scientific"], geography=combined["geography"],
          historical=combined["historical"], native_validations=combined["native_validations"],
          artifact_sha256=combined["artifact_sha256"], prior_repaired_sha256=REPAIRED_SHA,
          repaired_control_repeated=False, source_sha256=digest, waveform_reads=0))


def launch(root):
    from empty_bootstrap import checked
    import portable_orbit_0316_repair as repair

    checked(REPAIRED, REPAIRED_SHA)
    verified_port()
    repair.launch(root, worker_path=Path(__file__).resolve())
    compare(root)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "compare"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.action == "compare":
        from empty_bootstrap import load_runtime

        load_runtime()
    {"launch": launch, "worker": worker, "compare": compare}[args.action](args.root)
