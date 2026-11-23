"""Run the named ALGO08v3 research publication with opt-in constrained checks."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from functools import wraps
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from named_weak_exact import run as named_publication


FIRST_ARMS = {"stock": None, "prepared": None, "c0-first": "c0", "fitted-first": "fitted_c"}


def saved_digest(value):
    if not re.fullmatch(r"[0-9a-f]{64}", value.removeprefix("sha256:")):
        raise argparse.ArgumentTypeError("Expected a named detector SHA-256")
    return "sha256:" + value.removeprefix("sha256:")


def options(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("recording", "archive", "region", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--constrained", choices=FIRST_ARMS, default="stock")
    parser.add_argument("--saved", type=Path, help="Existing signed named-v3 20 ms detections")
    parser.add_argument("--saved-digest", type=saved_digest, help="Sealed digest of --saved")
    parser.add_argument("--saved-inventory", type=Path, help="Authenticated original inventory for --saved")
    args = parser.parse_args(argv)
    if (args.saved is None) != (args.saved_digest is None) or (args.saved_inventory and args.saved is None):
        parser.error("Provide --saved and --saved-digest together, with optional --saved-inventory")
    return args


def inventory_binding(recording, path, expected_session, expected_manifest):
    from leo.contracts.digests import canonical_digest

    inventory = json.loads(path.read_bytes())
    digest = canonical_digest(inventory)
    session = "fast-" + digest[7:39]
    root = recording.absolute()
    segments = inventory["segments"]
    if (digest != expected_manifest or session != expected_session or inventory["recording_name"] != root.name
            or not segments or inventory["window_count"] != sum(row["windows"] for row in segments)
            or any(not Path(row["path"]).is_absolute() or ".." in Path(row["path"]).parts
                   or not Path(row["path"]).is_relative_to(root) for row in segments)):
        raise ValueError("Expected the detection packet's original recording inventory")

    def metadata_only(_store, selected, *, verify_windows=True):
        if verify_windows or selected != recording:
            raise ValueError("The signed inventory authorizes metadata for the requested recording only")
        return session, digest, inventory

    return metadata_only


def deny_waveform(*args, **kwargs):
    raise RuntimeError("The saved publication must not read original waveform samples")


def observe_nominations(nominate, observations):
    @wraps(nominate)
    def observe(*args, **kwargs):
        result = nominate(*args, **kwargs)
        families = result["families"] if result["status"] == "complete" else ()
        offered = sum(f["best"] is not None and f["predictive_gain"] > 0 for f in families)
        observations.append(dict(status=result["status"], families=len(families), positive_offers=int(offered)))
        return result

    return observe


@contextmanager
def analysis_scope(args, native, audit):
    from leo.analysis.localization_v3 import family_cavity
    from tools import algo08_position

    selected = algo08_position.selected_packet

    @wraps(selected)
    def selected_packet(*values, **options):
        packet = selected(*values, **options)
        audit["selected_rows"] = {
            arm: [[row["observation_id"], row["norad"], row["role"]] for row in rows]
            for arm, rows in packet["rows"].items()
        }
        return packet

    with ExitStack() as scope:
        scope.enter_context(patch.object(
            family_cavity, "nominate_families", observe_nominations(family_cavity.nominate_families, audit["nominations"])
        ))
        scope.enter_context(patch.object(algo08_position, "selected_packet", selected_packet))
        if native is not None:
            from leo.storage.fast_scan import FastScanStore, FastSegmentSource
            from leo.storage.short_window import ShortWindowReader

            if args.saved_inventory is not None:
                source = native["source"]
                inventory = inventory_binding(args.recording, args.saved_inventory, source["session_id"],
                                              source["input_manifest_sha256"])
                scope.enter_context(patch.object(FastScanStore, "inventory", inventory))
            scope.enter_context(patch.object(FastSegmentSource, "windows", deny_waveform))
            scope.enter_context(patch.object(ShortWindowReader, "windows", deny_waveform))
        if args.constrained != "stock":
            from leo.analysis.localization_v3 import feasible
            from leo.analysis.research import polynomial_satellite_diagnostics, retained_track_likelihood
            from prepared_constrained_checks import RELEASE_SOURCES, gate_binding, validate_released_ports

            validate_released_ports(feasible, family_cavity, retained_track_likelihood, polynomial_satellite_diagnostics)
            audit["prepared_release_sources"] = RELEASE_SOURCES
            scope.enter_context(gate_binding(feasible, family_cavity, retained_track_likelihood, audit["prepared_counts"]))
            if audit["first_arm"] is not None:
                from constrained_pair_veto import guard

                scope.enter_context(guard(family_cavity, feasible, audit["pair_audit"], first_arm=audit["first_arm"]))
        yield


def run(args):
    from empty_bootstrap import checked, clock, now

    started = now()
    output = args.output.absolute()
    resolved = output.resolve()
    if resolved.is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("The fresh research output must be local")
    offer = args.region.read_bytes()
    json.loads(offer)
    if not args.archive.is_dir():
        raise ValueError("Expected a causal archive directory")
    native = None if args.saved is None else json.loads(checked(args.saved, args.saved_digest[7:]))
    first_arm = FIRST_ARMS[args.constrained]
    audit = dict(mode=args.constrained, first_arm=first_arm, nominations=[], selected_rows={},
                 prepared_counts=Counter(), pair_audit={}, prepared_release_sources={})
    sources = [Path(__file__), HERE / "named_weak_exact.py", HERE / "empty_bootstrap.py"]
    if args.constrained != "stock":
        sources.append(HERE / "prepared_constrained_checks.py")
    if first_arm is not None:
        sources.append(HERE / "constrained_pair_veto.py")
    pins = {path.name: "sha256:" + sha256(path.read_bytes()).hexdigest() for path in sources}

    output.mkdir()
    launch = SimpleNamespace(recording=args.recording, archive=args.archive, region=args.region, bulk_root=output)
    named_publication(launch, optimized=False, saved=args.saved, expected=args.saved_digest,
                      analysis_scope=lambda: analysis_scope(args, native, audit))

    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    named = json.loads((output / "named-weak-exact.json").read_bytes())
    publication = named["publication"]
    detail = FastStandardAnalysisStore(output).detail(publication["run_id"])
    identity = dict(named_specification=named["frozen_specification"], mode=args.constrained,
                    first_arm=first_arm, implementation=pins, release_ports=audit["prepared_release_sources"])
    audit.update(
        research_sha256=canonical_digest(identity), implementation=pins,
        named_specification=named["frozen_specification"], detector_sha256="sha256:"+named["detector_sha256"],
        saved_input_sha256=args.saved_digest, named_input_sha256=detail["input_sha256"],
        raw_authority=detail["raw_authority"], region_file_sha256="sha256:"+sha256(offer).hexdigest(),
        archive=str(args.archive), publication=publication, wall_and_process=clock(started),
    )
    with (output / "named-constrained-research.json").open("x") as stream:
        json.dump(audit, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    run(options())
