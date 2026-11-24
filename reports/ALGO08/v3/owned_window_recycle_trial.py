"""Measure exact owned-window leases at the current signed detector boundary."""

import argparse
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
from pathlib import Path
from resource import RUSAGE_SELF, RUSAGE_THREAD, getrusage
import sys
from time import perf_counter_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.append(str(ROOT))
from reports.ALGO08.v3 import original_prefix_scaling as prefix

PAST = Path("/tmp/leo-v3-original-prefix-scaling-0016-result01/binding.json")
PAST_PIN = "a506518c90dd3867b8f2f35af07bd024b44687622c5ca7d506f935b4b44bfe9c"
ORDERS = (("stock", "lease"), ("lease", "stock"))
SCOPE = 4
FULL_WINDOWS = 808
USEFUL_S = .25


def clock(scope):
    r = getrusage(scope)
    return (perf_counter_ns(), round(r.ru_utime * 1e9), round(r.ru_stime * 1e9),
            r.ru_minflt, r.ru_majflt, r.ru_inblock)


KEYS = ("wall_ns", "user_ns", "system_ns", "minor_faults", "major_faults", "input_blocks")


def delta(start, end):
    return {name: y - x for name, x, y in zip(KEYS, start, end, strict=True)}


class Trace:
    def __init__(self, arena):
        self.arena = arena
        self.members = []
        self.prefetch = []
        self.addresses = {}
        self.active = None

    def member(self, operation):
        def wrapped(source, chunk, *args, **kwargs):
            if self.active is not None:
                raise ValueError("Expected original members to be active serially")
            observed = dict(segment=source.reader.manifest_sha256, chunk=chunk.chunk_index,
                            bytes=chunk.compressed_bytes, windows=chunk.window_count,
                            decode=[], callback=[])
            self.active = observed
            stamp = clock(RUSAGE_SELF), clock(RUSAGE_THREAD)
            try:
                return (yield from operation(source, chunk, *args, **kwargs))
            finally:
                observed.update(whole_process=delta(stamp[0], clock(RUSAGE_SELF)),
                                main_thread=delta(stamp[1], clock(RUSAGE_THREAD)))
                self.members.append(observed)
                self.active = None

        return wrapped

    @contextmanager
    def binding(self):
        from reports.ALGO08.v3 import legacy_first_map_input as production, legacy_fused_map as fused
        from combined_frontier_run import load_prefetch
        import combined_frontier_run as frontier
        from leo.storage.short_window import ShortWindowReader
        from mixed_aperture_receiver import MixedApertureDetector

        probe = self
        stock_auth = ShortWindowReader._member
        stock_detector = MixedApertureDetector.detector

        class Observed(fused.FusedMember):
            def owned_output(self):
                if probe.arena is not None:
                    view = probe.arena.borrow(self.owned_capacity)
                    if view is not None:
                        return view
                return super().owned_output()

            def read_window(self, row):
                before = clock(RUSAGE_THREAD)
                raw = super().read_window(row)
                elapsed = delta(before, clock(RUSAGE_THREAD))
                address = raw.ctypes.data
                ident = probe.addresses.setdefault(address, len(probe.addresses))
                probe.active["decode"].append(dict(sequence=row.sequence, slot=ident, bytes=raw.nbytes, **elapsed))
                return raw

        def auth(reader, name, size, pin):
            observe = self.active is not None and name.endswith(".ci16.zst")
            if observe:
                start = clock(RUSAGE_THREAD)
            data = stock_auth(reader, name, size, pin)
            if observe:
                self.active["encoded_auth_main"] = delta(start, clock(RUSAGE_THREAD))
            return data

        @contextmanager
        def callbacks(detector, *args, **kwargs):
            with stock_detector(detector, *args, **kwargs) as ordinary:
                def receive(window):
                    start = clock(RUSAGE_THREAD)
                    factors = ordinary(window)
                    self.active["callback"].append(delta(start, clock(RUSAGE_THREAD)))
                    return factors

                yield receive

        def observed_prefetch():
            fetch = load_prefetch()
            scope = fetch.__wrapped__.__globals__
            read = scope["prefetch_member"]

            def measure(root, name, size, stats):
                start = clock(RUSAGE_THREAD)
                output = read(root, name, size, stats)
                self.prefetch.append(dict(segment=root.name, name=name, bytes=size, supplied=output is not None,
                                          **delta(start, clock(RUSAGE_THREAD))))
                return output

            @contextmanager
            def scoped():
                with patch.dict(scope, {"prefetch_member": measure}), fetch() as stats:
                    yield stats

            return scoped

        with (patch.object(fused, "FusedMember", Observed),
              patch.object(ShortWindowReader, "_member", auth),
              patch.object(MixedApertureDetector, "detector", callbacks),
              patch.object(production, "member_windows", self.member(production.member_windows)),
              patch.object(frontier, "load_prefetch", observed_prefetch)):
            yield


def worker(root, book, mode):
    import empty_bootstrap as boot

    before = clock(RUSAGE_SELF)
    load = boot.load_runtime
    with ExitStack() as patches:
        def loaded():
            result = load()
            from reports.ALGO08.v3.owned_window_recycle import WindowArena

            tracker = Trace(WindowArena() if mode == "lease" else None)
            patches.enter_context(tracker.binding())
            traces.append(tracker)
            return result

        traces = []
        patches.enter_context(patch.object(boot, "load_runtime", loaded))
        prefix.worker(root, book, SCOPE)
    (trace,) = traces
    audit = delta(before, clock(RUSAGE_SELF))
    (root / "memory.json").write_text(json.dumps(dict(mode=mode, process=audit, members=trace.members,
        total_addresses=len(trace.addresses), prefetch=trace.prefetch,
        arena=trace.arena.receipt() if trace.arena is not None else None), sort_keys=True) + "\n")


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import RELEASE
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident

    book = json.loads(prefix.pinned(PAST, PAST_PIN))
    paths = prefix.files(book, book["scopes"][str(SCOPE)])
    machine = host()
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root / name).mkdir()
    binding = root / "binding.json"
    write(binding, book)
    orders = []
    for index, order in enumerate(ORDERS):
        pair = {}
        for mode in order:
            output = root / f"{index}-{mode}"
            cached = resident(paths)
            command = [str(RELEASE / "venv/bin/python"), "-IB", str(Path(__file__).resolve()), "worker",
                       str(output), "--binding", str(binding), "--mode", mode]
            clock = measure(command, environment_for(root), output)
            pair[mode] = dict(clock=clock, command=command, before=cached, after=resident(paths), output=str(output))
            write(root / f"{output.name}-clock.json", pair[mode])
            if clock["exit_code"]:
                raise RuntimeError(clock["stderr_tail"])
        orders.append(pair)
    write(root / "launch.json", dict(machine=machine, order=ORDERS, rows=orders,
          binding_sha256=sha256(binding.read_bytes()).hexdigest()))


def total(rows):
    return {name: sum(row[name] for row in rows) for name in KEYS}


def score(root):
    from aperture_trial import write
    from visit_frame_raw_0016 import read

    book, manifest = read(root / "binding.json"), read(root / "launch.json")
    prefix.pinned(root / "binding.json", manifest["binding_sha256"])
    scope = book["scopes"][str(SCOPE)]
    prior = json.loads(prefix.pinned(prefix.PRIOR / "verified-once.json", prefix.PRIOR_PIN))
    wanted = [(r["member_sha256"], r["index_sha256"], r["raw_sha256"])
              for r in prior["checked"]["DS30-0016"]["original"]["members"][:SCOPE]]
    selected = []
    common = None
    for pair in manifest["rows"]:
        checked = {}
        for mode, entry in pair.items():
            output, timed = Path(entry["output"]), entry["clock"]
            data = (output / "detections.json").read_bytes()
            memory, live = read(output / "memory.json"), read(output / "worker.json")
            acquire = live["receiver"]["acquire"]
            original = live["source"]["members"]
            if common is None:
                common = data
            if (data != common or timed["exit_code"] or len(memory["members"]) != SCOPE
                    or [(r["member_sha256"], r["index_sha256"], r["raw_sha256"]) for r in original] != wanted
                    or sum(len(row["decode"]) for row in memory["members"]) != scope["stop"]
                    or len(live["iq"]) != scope["stop"]):
                raise ValueError("The observed receiver changed authenticated scope or detector bytes")
            main = total([m["main_thread"] for m in memory["members"]])
            decode = total([row for member in memory["members"] for row in member["decode"]])
            callback = total([row for member in memory["members"] for row in member["callback"]])
            encoded = total([m["encoded_auth_main"] for m in memory["members"]])
            speculative = total(memory["prefetch"])
            if encoded["input_blocks"] or speculative["input_blocks"]:
                raise ValueError("Expected only the admitted resident encoded input")
            checked[mode] = dict(acquire=acquire, clock=timed, memory=memory,
                launch_to_detector_s=(live["detector_published_unix_ns"] - timed["started_unix_ns"]) / 1e9,
                main=main, decode=decode, callback=callback, encoded=encoded, speculative=speculative,
                output_capacity=original[0]["owned_window_capacity"])
        selected.append(checked)
    extrapolation = FULL_WINDOWS / scope["stop"]
    savings = [(p["stock"]["acquire"]["cpu_ns"] - p["lease"]["acquire"]["cpu_ns"]) / 1e9
               for p in selected]
    scoped = [((p["stock"]["decode"]["system_ns"] + p["stock"]["decode"]["user_ns"])
               - (p["lease"]["decode"]["system_ns"] + p["lease"]["decode"]["user_ns"])) / 1e9
              for p in selected]
    write(root / "result.json", dict(case="DS30-0016", bytes=scope["bytes"], windows=scope["stop"],
          detector_sha256=sha256(common).hexdigest(), pairs=selected, launches=manifest, extrapolation=extrapolation,
          extrapolated_acquisition_s=[time * extrapolation for time in savings],
          extrapolated_decode_s=[time * extrapolation for time in scoped],
          advance=all(time * extrapolation >= USEFUL_S for time in (*savings, *scoped))))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--binding", type=Path)
    cli.add_argument("--mode", choices=("stock", "lease"))
    args = cli.parse_args()
    if args.action == "launch":
        launch(args.root)
    elif args.action == "worker":
        worker(args.root, json.loads(args.binding.read_bytes()), args.mode)
    else:
        score(args.root)
