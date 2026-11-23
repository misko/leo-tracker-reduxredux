"""Observe exact orbit and phase setup requests on the pinned weak saved solve."""

from argparse import ArgumentParser
from collections import Counter
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from struct import pack
from sys import _getframe
from time import process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, read, solve, write
from dense_geographic_trial import elapsed, host, now


HERE = Path(__file__).resolve().parent
CONTROL = HERE / "measurements/weak-combined-raw.json"
INPUT_PINS = {
    "score": "a704861e37e40e7364fbf97bcb74e98bb9c701ca474c12821e8ed7df86cab233",
    "recipe": "d708b22baa7c48acc8db5dec7925fb5528b61000a601638c53b6340ea0891f5b",
    "research": "a949e4388eb483207a4c6c7e286afb86c146e0ea5c0f2104ec239a594062c5c8",
    "tracks": "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a",
}
OWNER_KEYS = ("observation_id", "norad", "role")
KNOWN_PAIR = frozenset(("regional_bank", "regional_proof"))


@dataclass
class BulkCall:
    stage: str
    keys: tuple
    state: object
    cpu_ns: int


def stage():
    frame = _getframe(2)
    direct = frame.f_code.co_name
    while frame is not None:
        name = frame.f_code.co_name
        if name == "causal_probes":
            return "regional_proof"
        if name in ("regional_bank", "previous_bank", "reference_motion_basis", "build_modes"):
            return name
        frame = frame.f_back
    return direct


def compare_bulk(calls):
    """Count exact later cells once, giving the already studied pair first claim."""
    import numpy as np

    details = []
    for index, current in enumerate(calls):
        state = current.state
        keys = {key: j for j, key in enumerate(current.keys)}
        if len(keys) != len(current.keys) or len(set(state.utc_ns)) != len(state.utc_ns):
            raise ValueError("A propagated matrix repeats an element key or UTC internally")
        claimed = np.zeros(state.error_code.shape, dtype=bool)
        overlaps = Counter()
        changed = 0
        order = sorted(range(index), key=lambda i: (
            frozenset((calls[i].stage, current.stage)) != KNOWN_PAIR, i))
        for i in order:
            old = calls[i]
            _, old_time, new_time = np.intersect1d(old.state.utc_ns, state.utc_ns, return_indices=True)
            pairs = [(j, keys[key]) for j, key in enumerate(old.keys) if key in keys]
            if not len(old_time) or not pairs:
                continue
            old_row, new_row = zip(*pairs, strict=True)
            old_at, new_at = np.ix_(old_row, old_time), np.ix_(new_row, new_time)
            identical = old.state.error_code[old_at] == state.error_code[new_at]
            for name in ("position_teme_km", "velocity_teme_km_s"):
                original = getattr(old.state, name).view(np.uint64)[old_at]
                duplicate = getattr(state, name).view(np.uint64)[new_at]
                identical &= (original == duplicate).all(axis=-1)
            new = identical & ~claimed[new_at]
            overlaps[old.stage] += int(new.sum())
            changed += int((~identical).sum())
            claimed[new_at] |= identical
        known = sum(count for source, count in overlaps.items()
                    if frozenset((source, current.stage)) == KNOWN_PAIR)
        new = int(claimed.sum()) - known
        details.append(dict(stage=current.stage, orbits=len(current.keys), knots=len(state.utc_ns),
                            cells=claimed.size, cpu_ns=current.cpu_ns, known_overlap=known, new_overlap=new,
                            previous_stage_cells={name: count for name, count in overlaps.items() if count},
                            disagreeing_comparisons=changed))
    return details


class Trace:
    def __init__(self):
        self.elements = {}
        self.lines = set()
        self.phase_lines = set()
        self.scalar_states = {}
        self.snapshots = set()
        self.calls = []
        self.phase = Counter()
        self.records = Counter()
        self.trace_cpu_ns = 0

    def bind(self, element, lines):
        # Keep a strong reference so an unmatched generated orbit cannot reuse an id.
        self.elements[id(element)] = (element, lines)
        self.lines.add(lines)
        return element

    def parse_elements(self, base):
        def parse(first, second):
            result = base(first, second)
            start = process_time_ns()
            self.bind(result, (first, second))
            self.trace_cpu_ns += process_time_ns() - start
            return result

        return SimpleNamespace(twoline2rv=parse)

    def phase_elements(self, base):
        def parse(first, second):
            start = process_time_ns()
            result = base(first, second)
            duration = process_time_ns() - start
            lines = first, second
            self.phase.update(parse_calls=1, parse_cpu_ns=duration)
            if lines in self.phase_lines:
                self.phase.update(repeated_parse_calls=1, repeated_parse_cpu_ns=duration)
            elif lines in self.lines:
                self.phase.update(preparsed_elsewhere_calls=1, preparsed_elsewhere_cpu_ns=duration)
            self.phase_lines.add(lines)

            def propagate(day, fraction):
                start = process_time_ns()
                value = result.sgp4(day, fraction)
                duration = process_time_ns() - start
                self.phase.update(state_calls=1, state_cpu_ns=duration)
                key = lines, pack("2d", day, fraction)
                status, p, v = value
                bits = pack("i6d", status, *p, *v)
                previous = self.scalar_states.setdefault(key, None)
                if previous is None:
                    self.scalar_states[key] = bits
                elif previous == bits:
                    self.phase.update(repeated_state_calls=1, repeated_state_cpu_ns=duration)
                else:
                    self.phase["disagreeing_states"] += 1
                return value

            return SimpleNamespace(sgp4=propagate)

        return SimpleNamespace(twoline2rv=parse)

    def snapshot_parser(self, base):
        def parse(snapshot):
            start = process_time_ns()
            result = base(snapshot)
            duration = process_time_ns() - start
            self.records.update(calls=1, cpu_ns=duration, records=len(result))
            if snapshot in self.snapshots:
                self.records.update(repeated_calls=1, repeated_cpu_ns=duration, repeated_records=len(result))
            self.snapshots.add(snapshot)
            return result

        return parse

    def propagator(self, base):
        def propagate(catalogue, grid, indices=None):
            start = process_time_ns()
            result = base(catalogue, grid, indices)
            duration = process_time_ns() - start
            overhead = process_time_ns()
            selected = catalogue.satellites if indices is None else [catalogue.satellites[j] for j in indices]
            keys = []
            for element in selected:
                identity = id(element)
                if identity not in self.elements:
                    self.elements[identity] = (element, identity)
                keys.append(self.elements[identity][1])
            self.calls.append(BulkCall(stage(), tuple(keys), result, duration))
            self.trace_cpu_ns += process_time_ns() - overhead
            return result

        return propagate

    @contextmanager
    def observe(self):
        from leo.analysis.localization_v3 import orbits, phase_prior
        from leo.sky import propagation
        from tools.pipeline_eval.variants import algo08_causal_reuse

        parse = self.snapshot_parser(propagation.parse_element_set_records)
        if algo08_causal_reuse.parse_element_set_records is not propagation.parse_element_set_records:
            raise ValueError("The two installed causal validation ports diverged")
        with (patch.object(propagation, "parse_element_set_records", parse),
              patch.object(algo08_causal_reuse, "parse_element_set_records", parse),
              patch.object(propagation, "Satrec", self.parse_elements(propagation.Satrec.twoline2rv)),
              patch.object(algo08_causal_reuse, "Satrec", self.parse_elements(algo08_causal_reuse.Satrec.twoline2rv)),
              patch.object(phase_prior, "Satrec", self.phase_elements(phase_prior.Satrec.twoline2rv)),
              patch.object(orbits, "propagate_grid", self.propagator(orbits.propagate_grid))):
            yield


def file_hash(path):
    return sha256(path.read_bytes()).hexdigest()


def pinned(path, digest):
    if file_hash(path) != digest:
        raise ValueError(f"Unexpected sealed bytes for {path}")
    return read(path)


def bound_input():
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest

    record = pinned(CONTROL, INPUT_PINS["score"])
    binding = record["binding"]
    request = binding["request"]
    command = binding["commands"]["candidate"]
    root = Path(command[command.index("--output") + 1])
    audit = pinned(root / "full-short-recipe.json", INPUT_PINS["recipe"])
    research = pinned(root / "joint-research-receipt.json", INPUT_PINS["research"])
    control = record["runs"]["candidate"]
    native_path, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    terminal = read(native_path.parents[1] / research["receipt"]["run_id"] / "terminal.json")
    native = read(native_path)
    source = native["source"]
    archive = Path(request["archive"]["root"])
    region = Algo08Region.parse(pinned(Path(request["region_file"]), request["offer_sha256"])).document()
    geographic = Path(command[command.index("--geographic-library") + 1])
    if (file_hash(geographic) != audit["geographic_sha256"] or audit["graph"] != "installed"
            or not audit["reuse_cold_track_rows"] or not audit["reuse_grid_phase_states"]
            or not research["optimized_full_catalogue"] or not research["signed_finish"]
            or research["receipt"]["decision"] != "complete"
            or archive_identity(archive) != request["archive"] or terminal["region"] != region
            or region != request["offered_region"] or terminal["session_id"] != request["session"]
            or source["session_id"] != request["session"] or source["input_manifest_sha256"] != binding["inventory"]
            or source["raw_recording_authority_digest"] != request["raw_authority"]
            or terminal["native_sha256"] != control["native_sha256"]
            or canonical_digest(native) != control["native_sha256"]
            or canonical_digest(terminal) != control["terminal_sha256"]):
        raise ValueError("Saved weak detector, original geographic proof, or route binding diverged")
    for name, digest in research["source_sha256"].items():
        if not name.startswith("installed/") and file_hash(HERE / name) != digest:
            raise ValueError(f"Archived candidate module changed: {name}")
    return native, archive, region, geographic, control, research, request


def budgets(rows, observer):
    def overlap_ns(field):
        return sum(row["cpu_ns"] * row[field] / row["cells"] for row in rows if row["cells"])

    new_ns = sum(observer.phase[name] for name in ("repeated_parse_cpu_ns", "preparsed_elsewhere_cpu_ns",
                                                   "repeated_state_cpu_ns")) + observer.records["repeated_cpu_ns"]
    return dict(known_partial_cell_estimate_ns=overlap_ns("known_overlap"),
                new_partial_cell_estimate_ns=overlap_ns("new_overlap"),
                new_whole_call_ns=sum(r["cpu_ns"] for r in rows if r["cells"] and r["new_overlap"] == r["cells"]),
                new_affected_call_inclusive_ns=sum(r["cpu_ns"] for r in rows if r["new_overlap"]) + new_ns,
                new_total_cell_proportional_ns=overlap_ns("new_overlap") + new_ns)


def run(output):
    machine = host()
    publication, specification = configuration()
    from leo.contracts.digests import canonical_digest

    from cold_track_row_entry import cold_track_rows
    from early_region import before_fit
    from full_short_run import geographic_projection
    from grid_phase_state_reuse import cached_predictive_grid
    from joint_publication import full_catalogue_route
    from optimized_grid import reduced_grid
    from prepared_exterior import handoff
    from tools import algo08_position
    from tools.pipeline_eval.variants import algo08_causal_table, v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard as guard

    native, archive, offer, binary, control, research, request = bound_input()
    original = algo08_position.solve
    attempts, proofs = [], []
    observer = Trace()
    extra, counts = {}, {}
    causal = algo08_causal_table.causal_table
    tables = []

    @contextmanager
    def causal_counters(**kwargs):
        with causal(**kwargs) as table:
            tables.append(table)
            yield table

    def observed(document, reader, assets, region):
        if (document is not native or reader.root != archive or region.document() != offer
                or file_hash(assets / "tracks.json") != INPUT_PINS["tracks"]):
            raise ValueError("Saved handoff differs from the installed-graph candidate")
        start = now()
        with ExitStack() as scopes:
            scopes.enter_context(observer.observe())
            for key, context in (("cold_track_rows", cold_track_rows()),
                                 ("geographic_projector", geographic_projection(binary)),
                                 ("reduced_grid", reduced_grid()),
                                 ("predictive_phase_states", cached_predictive_grid())):
                counts[key] = scopes.enter_context(context)
            live, counts["prepared_exterior"], _ = scopes.enter_context(handoff(reader))
            full = full_catalogue_route(v5_core.infer, reader, attempts, optimized=True)
            route = before_fit(full, reader, guard.causal_probes, proofs, live.match)
            scopes.enter_context(patch.object(v5_core, "infer", route))
            decision, packet, policy = original(document, reader, assets, region)
        extra["solve_clock"] = elapsed(start)
        extra["solve_counters"] = {name: dict(value) for name, value in counts.items()}
        if packet is None or not packet["position_grid"]["complete"]:
            raise ValueError("The original solver did not complete the genuine numerical grid")
        extra["owner_rows"] = {arm: [[r[k] for k in OWNER_KEYS] for r in packet["rows"][arm]] for arm in ARMS}
        return decision, packet, policy

    with (patch.object(algo08_causal_table, "causal_table", causal_counters),
          patch.object(algo08_position, "solve", observed)):
        result = solve(publication, specification, native, archive, offer)
    proof, = proofs
    original_proof, = research["early_regional"]
    control_solve = research["solve"]
    checks = dict(
        status=result["status"] == "ok", policy=result["orbit_policy"] == control_solve["orbit_policy"],
        arms=all(list(result["arms"][arm]["latlon"]) == control["arms"][arm]["latlon"]
                 and result["arms"][arm]["rf_rms_hz"] == control["arms"][arm]["rf_rms_hz"] for arm in ARMS),
        owners=result["owners"] == control["owners"], owner_rows=extra.pop("owner_rows") == research["selected_rows"],
        zero_objective_replay=result["objective_replay"] == dict.fromkeys(ARMS, 0.0),
        grid_points=result["grid_points"] == control["grid_points"], science=result["science"] == control["scientific_digests"],
        route=len(attempts) == 1 and attempts[0]["decision"] == research["route"],
        tle_records=result["tle_records"] == research["receipt"]["tle_records"],
        proof_result=canonical_digest(proof["result"]) == canonical_digest(original_proof["result"]),
        proof_reuse=proof["reused"] == original_proof["reused"],
        causal_table=len(tables) == 1,
    )
    if not all(checks.values()):
        failed = ", ".join(name for name, equal in checks.items() if not equal)
        raise ValueError(f"Instrumented replay diverged from the original in {failed}")
    result.pop("owner_rows")
    start = now()
    rows = compare_bulk(observer.calls)
    overhead = elapsed(start)
    write(output, dict(case="DS30-0016", machine=machine, request=request, raw_native=control["native_sha256"],
                       raw_terminal=control["terminal_sha256"], pins=INPUT_PINS,
                       source_sha256=file_hash(Path(__file__)), archive_control_cpu_s=control_solve["cpu_s"],
                       result=result, checks=checks, proof=proof, causal_table=tables[0], bulk_calls=rows,
                       scalar_phase=dict(observer.phase), snapshot_parse=dict(observer.records),
                       trace_hook_partial_cpu_ns=observer.trace_cpu_ns, matrix_audit=overhead,
                       budget=budgets(rows, observer), **extra))


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
