"""Run the guarded selective raw receiver with repaired source indexing and optional exact block rank."""

import argparse
from contextlib import ExitStack, contextmanager, nullcontext
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import runpy
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


@dataclass(frozen=True, slots=True)
class Portable:
    file: Path
    sha256: str
    producer_sha256: str | None = None

    def arguments(self):
        result = ["--portable-orbit-index", str(self.file), "--portable-orbit-index-sha256", self.sha256]
        if self.producer_sha256 is not None:
            result.extend(("--portable-orbit-producer-sha256", self.producer_sha256))
        return result


def portable_factory(request, audit):
    from empty_bootstrap import checked
    from historical_orbit_index import SourceIndex
    from portable_orbit_compatibility import producer_versions
    from portable_orbit_index import PortableSourceIndex, load_index, versions

    start = process_time_ns(), perf_counter_ns()
    entry = dict(file=str(request.file), sha256=request.sha256, producer_sha256=request.producer_sha256)
    audit.setdefault("transfers", []).append(entry)
    try:
        if request.producer_sha256 is None:
            compatibility = versions()
        else:
            manifest = request.file.parent/"artifact-bind.json"
            producer = json.loads(checked(manifest, request.producer_sha256.removeprefix("sha256:")))
            if producer["portable_sha256"] != request.sha256:
                raise ValueError("Trusted producer manifest names a different orbit index")
            compatibility = producer_versions(producer["implementation"])
            entry["producer_cutoff_utc_ns"] = producer["source"]["cutoff_utc_ns"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        entry["compatibility"] = dict(fallback=str(error), cpu_ns=process_time_ns()-start[0], elapsed_ns=perf_counter_ns()-start[1])
        return SourceIndex()
    entry["compatibility"] = dict(fallback=None, cpu_ns=process_time_ns()-start[0], elapsed_ns=perf_counter_ns()-start[1])
    artifact, entry["loading"] = load_index(request.file, request.sha256, compatibility)
    if artifact is None:
        return SourceIndex()
    index = PortableSourceIndex(artifact)
    entry["counts"] = index.counts
    return index


@contextmanager
def combined_runtime(orbit, rank, portable=None, *, use_blocks=False):
    import empty_bootstrap
    from north_orbit_index_raw import bind_runtime

    factory = None if portable is None else lambda: portable_factory(portable, orbit)
    with ExitStack() as scope:
        scope.enter_context(bind_runtime(orbit, index_factory=factory))
        if use_blocks:
            original = empty_bootstrap.load_runtime

            def load():
                runtime = original()
                from catalogue_block_port import use_catalogue_blocks

                rank["counts"] = scope.enter_context(use_catalogue_blocks())
                return runtime

            scope.enter_context(patch.object(empty_bootstrap, "load_runtime", load))
        yield


def rank_status(requested, audit):
    if not requested:
        return "disabled"
    counts = audit.get("counts", {})
    if counts.get("compact_calls", 0):
        return "compacted"
    if counts.get("admitted_ranks", 0) or counts.get("original_ranks", 0):
        return "original_scoring_only"
    return "no_compatible_rank_scope"


def read_options(cli, args):
    if (args.portable_orbit_index is None) != (args.portable_orbit_index_sha256 is None):
        cli.error("Provide both the portable orbit index and its trusted SHA-256")
    if args.portable_orbit_producer_sha256 is not None and args.portable_orbit_index is None:
        cli.error("The producer pin requires a portable orbit index")
    if args.portable_orbit_index is None:
        return None
    for pin in (args.portable_orbit_index_sha256, args.portable_orbit_producer_sha256):
        if pin is not None and (len(pin.removeprefix("sha256:")) != 64
                                or any(char not in "0123456789abcdef" for char in pin.removeprefix("sha256:"))):
            cli.error("Invalid SHA-256 digest")
    pin = "sha256:" + args.portable_orbit_index_sha256.removeprefix("sha256:")
    return Portable(args.portable_orbit_index, pin, args.portable_orbit_producer_sha256)


def add_options(cli):
    cli.add_argument("--catalogue-block-rank", action="store_true", help="Use exact catalogue blocks in compatible shared cold ranks")
    cli.add_argument("--portable-orbit-index", type=Path, help="Cold source indexing is the default")
    cli.add_argument("--portable-orbit-index-sha256", help="Trusted digest of the prebuilt index")
    cli.add_argument("--portable-orbit-producer-sha256", help="Trusted digest of sibling artifact-bind.json")


def main(argv=None):
    from continued_cfo import raw_entry

    cli = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    cli.add_argument("-h", "--help", action="store_true")
    receiver = cli.add_mutually_exclusive_group(required=True)
    receiver.add_argument("--anchored-cfo-pack", type=Path)
    receiver.add_argument("--eight-ms-native-history", action="store_true")
    cli.add_argument("--short-timing-scout", type=Path, help="Pinned alternate guarded short timing object")
    cli.add_argument("--short-timing-scout-sha256", help="Expected short-scout.json digest")
    cli.add_argument("--output", type=Path)
    add_options(cli)
    argv = sys.argv[1:] if argv is None else argv
    if any(flag in argv for flag in ("-h", "--help")):
        cli.print_help()
        if not any(option.split("=", 1)[0] in ("--anchored-cfo-pack", "--eight-ms-native-history") for option in argv):
            return
    args, inherited = cli.parse_known_args(argv)
    timing = nullcontext()
    if args.short_timing_scout is not None or args.short_timing_scout_sha256 is not None:
        if args.anchored_cfo_pack is None or args.short_timing_scout is None or args.short_timing_scout_sha256 is None:
            cli.error("The alternate scout needs its pack, digest and the original guarded CFO pack")
        from all_visit_timing import activate

        timing = activate(args.short_timing_scout, args.short_timing_scout_sha256)
    if args.help:
        inherited.append("--help")
    portable = read_options(cli, args)
    if args.output is not None:
        inherited.extend(("--output", str(args.output)))
    orbit, rank = {"requested": "cold" if portable is None else "portable"}, {"requested": args.catalogue_block_rank}
    with timing, combined_runtime(orbit, rank, portable, use_blocks=args.catalogue_block_rank):
        if args.eight_ms_native_history:
            native_eight(inherited)
        else:
            raw_entry(None, inherited, guarded_pack=args.anchored_cfo_pack)
    orbit["adapter_sha256"] = sha256((HERE/"historical_orbit_index.py").read_bytes()).hexdigest()
    rank["status"] = rank_status(args.catalogue_block_rank, rank)
    for name, doc in (("orbits-indexed.json", orbit), ("catalogue-block-rank.json", rank)):
        with (args.output.parent/name).open("x") as stream:
            json.dump(doc, stream, sort_keys=True, allow_nan=False)
            stream.write("\n")


def native_eight(argv):
    entry = HERE/"unified_short_bootstrap.py"
    with patch.object(sys, "argv", [str(entry), *argv, "--held-anchor-route", "--eight-ms-native-history"]):
        runpy.run_path(str(entry), run_name="__main__")


if __name__ == "__main__":
    main()
