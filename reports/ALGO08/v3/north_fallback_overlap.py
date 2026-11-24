"""Watch exact eligible operations in one saved North fallback publication."""

from contextlib import ExitStack, contextmanager
from dataclasses import fields, is_dataclass
from hashlib import sha256
import json
from pathlib import Path
from struct import pack
import sys
from time import perf_counter, process_time, process_time_ns
from unittest.mock import patch


ROOT = Path("/dev/shm/leo-live-stereo-north.BYuWvuyj/pair")
PINS = {
    "binding.json": "94dc2ebad1e6d1aecb98206f57ee1661a50cfdc054364a50504f30e358356f22",
    "masked/unified-short-bootstrap.json": "cfd9cb7e5d2ff2bebb6176ec8afb7c28bf7688b187d8e27419e562f54a940e11",
    "masked/joint-research-receipt.json": "5bc0a572cd6e273ca83e2e3ba77b3c8678c1a38f1e6ed86b0c8ab04071509b0d",
}


def fingerprint(value):
    """Preserve numeric types, signed zero, binary values, shape and sequence order."""
    import numpy as np

    digest = sha256()

    def add(node):
        kind = type(node)
        digest.update(f"{kind.__module__}.{kind.__qualname__}\0".encode())
        if kind is np.ndarray or isinstance(node, np.generic):
            array = np.asarray(node)
            if array.dtype.hasobject or array.dtype.fields is not None:
                raise ValueError("An object or structured array cannot supply a numeric fingerprint")
            add(array.dtype.str)
            add(array.shape)
            digest.update(memoryview(np.ascontiguousarray(array).reshape(-1)).cast("B"))
        elif is_dataclass(node):
            add(tuple(getattr(node, field.name) for field in fields(node)))
        elif kind in (tuple, list, dict):
            digest.update(pack(">Q", len(node)))
            for item in node.items() if kind is dict else node:
                add(item)
        elif kind is float:
            digest.update(pack(">d", node))
        elif kind in (str, bytes, int, bool) or node is None:
            payload = node if kind is bytes else repr(node).encode()
            digest.update(pack(">Q", len(payload)))
            digest.update(payload)
        else:
            raise ValueError(f"Cannot fingerprint {kind.__name__}")

    add(value)
    return digest.hexdigest()


class Watch:
    def __init__(self):
        self.phase = "early_regional"
        self.constructor = None
        self.inside_rank = False
        self.objects = {}
        self.scans = {}
        self.nominal = {}
        self.rows = []

    def identity(self, value):
        # Retain objects throughout this one inference, including the common prepared bank.
        key = id(value)
        self.objects.setdefault(key, value)
        return key

    @contextmanager
    def scoped(self, field, value):
        old = getattr(self, field)
        setattr(self, field, value)
        try:
            yield
        finally:
            setattr(self, field, old)

    def operation(self, name, key, key_ns, work, evidence=lambda value: value, *, prior_fingerprint_ns=0):
        start = process_time_ns()
        value = work()
        cpu = process_time_ns() - start
        start = process_time_ns()
        output = None
        if key is not None:
            try:
                output = fingerprint(evidence(value))
            except (TypeError, ValueError):
                pass
        fingerprint_ns = process_time_ns() - start + prior_fingerprint_ns
        self.rows.append(dict(operation=name, phase=self.phase, key=key, result_sha256=output,
                              operation_cpu_ns=cpu, key_cpu_ns=key_ns,
                              fingerprint_cpu_ns=fingerprint_ns, nested_rank=self.inside_rank))
        return value

    def report(self):
        seen = {}
        for row in self.rows:
            if row["key"] is None or row["result_sha256"] is None:
                continue
            key = row["operation"], row["key"]
            candidates = seen.setdefault(key, {})
            if row["phase"] == "fallback":
                row["earlier_phases"] = sorted(candidates)
                row["matches"] = sorted(phase for phase, results in candidates.items()
                                        if row["result_sha256"] in results)
            else:
                candidates.setdefault(row["phase"], set()).add(row["result_sha256"])
        # Replace process-local object addresses with stable receipt labels.
        names = {key: f"object_{number}" for number, key in enumerate(self.objects, 1)}

        def stable(key):
            if isinstance(key, tuple):
                return [stable(part) for part in key]
            return names.get(key, key)

        return [dict(row, key=stable(row["key"])) for row in self.rows]


@contextmanager
def observe(watch):
    import joint_publication
    from leo.analysis.localization_v3 import discovery, scan as scan_module
    from terminal_proof_reuse import CERTIFICATES, graph_inputs
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard as regional

    build = joint_publication.full_catalogue_route
    context, rank = v5_core.scan_context, v5_core.ranked_initial_nodes
    proof = regional.causal_probes
    geometry = scan_module.prepare_phase_geometry
    project = discovery.phase_linear_frequency

    def route(installed, *args, **kwargs):
        def fallback(*values, **options):
            with watch.scoped("phase", "fallback"):
                return installed(*values, **options)

        candidate = build(fallback, *args, **kwargs)

        def compare(*values, **options):
            with watch.scoped("phase", "candidate"):
                return candidate(*values, **options)

        return compare

    def scan_context(prepared, region, noise_digest, bound, previous):
        start = process_time_ns()
        prepared_key = watch.identity(prepared)
        scan_key = (prepared_key, watch.identity(region), noise_digest, watch.identity(bound), previous)
        key_time = process_time_ns() - start
        with watch.scoped("constructor", prepared_key):
            result = watch.operation("scan_context", None, key_time,
                                     lambda: context(prepared, region, noise_digest, bound, previous))
        watch.scans[watch.identity(result)] = scan_key
        watch.nominal[watch.identity(result.geometry)] = prepared_key
        return result

    def prepare_geometry(*args, **kwargs):
        start = process_time_ns()
        key = watch.constructor if len(args) == 2 and not kwargs else None
        if key is None:
            return geometry(*args, **kwargs)
        return watch.operation("nominal_geometry", key, process_time_ns() - start,
                               lambda: geometry(*args, **kwargs))

    def projection(grid, lat, lon, *, altitude_m=0.0, rf_hz=11.5e9):
        start = process_time_ns()
        nominal_key = watch.nominal.get(id(grid))
        if nominal_key is None:
            return project(grid, lat, lon, altitude_m=altitude_m, rf_hz=rf_hz)
        key = nominal_key, pack(">4d", lat, lon, altitude_m, rf_hz).hex()
        return watch.operation("nominal_discovery_projection", key, process_time_ns() - start,
                               lambda: project(grid, lat, lon, altitude_m=altitude_m, rf_hz=rf_hz))

    def initial_rank(scan):
        start = process_time_ns()
        key = watch.scans.get(id(scan))
        key_time = process_time_ns() - start
        start = process_time_ns()
        before = fingerprint((scan.reference, scan.element_derivatives))
        before_ns = process_time_ns() - start
        return watch.operation("ranked_initial_nodes", key, key_time, lambda: scoped_rank(scan),
                               lambda nodes: (before, nodes, scan.reference, scan.element_derivatives),
                               prior_fingerprint_ns=before_ns)

    def scoped_rank(scan):
        with watch.scoped("inside_rank", True):
            return rank(scan)

    def causal_probes(tracks, archive, region, *, catalogue=None, terminal_only=False):
        start = process_time_ns()
        key = None
        if catalogue is not None and terminal_only:
            key = (watch.identity(tracks), tracks["metadata"]["causal_cutoff_utc_ns"],
                   type(archive).__qualname__, str(archive.root), watch.identity(region),
                   watch.identity(catalogue), terminal_only, fingerprint(graph_inputs(tracks)))
        return watch.operation("terminal_regional_proof", key, process_time_ns() - start,
                               lambda: proof(tracks, archive, region, catalogue=catalogue, terminal_only=terminal_only),
                               evidence=eligible_proof)

    def eligible_proof(value):
        if (value.get("complete") is not False or value.get("would_withhold") is not False
                or value.get("stop") not in CERTIFICATES):
            raise ValueError("Only a certified early negative answer may be reused")
        return value

    with ExitStack() as stack:
        for module, port, observer in (
            (joint_publication, "full_catalogue_route", route), (v5_core, "scan_context", scan_context),
            (v5_core, "ranked_initial_nodes", initial_rank), (scan_module, "prepare_phase_geometry", prepare_geometry),
            (discovery, "phase_linear_frequency", projection), (regional, "causal_probes", causal_probes),
        ):
            stack.enter_context(patch.object(module, port, observer))
        yield


def verified_inputs(staged):
    from aperture_trial import archive_identity
    from combined_frontier_run import BLOCK_SHA
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from grid_feature_projection import LIBRARY_SHA
    from raw_cfo_north_trial import ORDER, native_file

    binding, raw, control = (json.loads(staged.checked(ROOT / name, digest)) for name, digest in PINS.items())
    request = binding["request"]
    command = binding["commanded"]["masked"]
    request["libraries"] = {}
    for flag, pin in (("geographic-library", GEOGRAPHIC_SHA), ("regional-track-library", TRACK_SCORES_SHA),
                      ("frontier-block-library", BLOCK_SHA), ("grid-feature-projection-library", LIBRARY_SHA)):
        path = command[command.index("--" + flag) + 1]
        staged.checked(Path(path), pin)
        request["libraries"][flag.replace("-", "_")] = path
    offer = Path(request["inside_offer"])
    staged.checked(offer, request["inside_offer_sha256"])
    request["offer_sha256"] = {ORDER[1]: request["inside_offer_sha256"]}
    staged.checked(Path(request["saved_inventory"]), request["inventory"][7:])
    packet = native_file(ROOT / "masked")
    native = json.loads(staged.checked(packet, raw["native_sha256"][7:]))
    staged.bind_native(native, request["session"], request["inventory"], raw["detector_recipe_sha256"][7:], expected=raw["native_sha256"])
    if (raw["receipt"] != control["receipt"] or raw["receipt"]["decision"] != "complete"
            or raw["requested_offer_sha256"] != request["inside_offer_sha256"] or raw["raw_acquisitions"] != 1
            or raw["verified_handoffs"] != 1 or raw["causal_cutoff_utc_ns"] != request["cutoff_utc_ns"]
            or native["source"]["raw_recording_authority_digest"] != request["authority"]
            or archive_identity(Path(request["archive"]["root"])) != request["archive"]):
        raise ValueError("The masked North source or causal authority changed")
    return request, offer, packet, native, raw, control


def archived_sources(source):
    # The archived source tree is the same one that produced the signed packet.
    verified = {}
    for filename, seal in PINS.items():
        data = (ROOT / filename).read_bytes()
        if sha256(data).hexdigest() != seal:
            raise ValueError(f"The historical receipt changed: {filename}")
        pins = json.loads(data).get("source_sha256", {})
        if filename == "binding.json":
            continue
        for name, digest in pins.items():
            if name.startswith("installed/"):
                continue
            if sha256((source / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"The replay source differs from the signed control: {name}")
            verified[name] = digest
    return verified


def worker(output, source):
    started = process_time(), perf_counter()
    verified_sources = archived_sources(source)
    sys.path.insert(0, str(source))
    import empty_bootstrap as staged

    runtime = staged.load_runtime()
    from aperture_trial import write
    from raw_cfo_north_trial import publish_saved

    request, offer, packet, native, raw, control = verified_inputs(staged)
    watch = Watch()
    with observe(watch):
        publish_saved(request, output, offer, packet, native, raw, started=started, runtime=runtime,
                      receipt_name="saved-overlap.json")
    current = json.loads((output / "joint-research-receipt.json").read_bytes())
    handoff = json.loads((output / "saved-overlap.json").read_bytes())
    parity = {key: current[key] == control[key] for key in ("evidence", "selected_rows", "selected_roles")}
    keys = ("run_id", "session_id", "counts", "region", "decision", "terminal_sha256")
    parity.update({key: current["receipt"][key] == control["receipt"][key] for key in keys})
    parity["fallback"] = all(current["route_details"][key] == control["route_details"][key]
                             for key in ("decision", "reason"))
    parity["early_proof"] = current["early_regional"][0]["result"] == control["early_regional"][0]["result"]
    write(output / "audit.json", dict(pins=PINS, control_sources=verified_sources,
          authority=request["authority"], archive=request["archive"],
          native_sha256=handoff["native_sha256"], verified_handoffs=handoff["handoffs"], waveform_calls=handoff["waveform_calls"],
          original_fallback=control["route_details"]["fallback_clocks"],
          trace_fallback=current["route_details"]["fallback_clocks"], parity=parity, operations=watch.report(),
          artifacts=current["evidence"], publication_s=handoff["complete_saved_s"],
          source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    if not all(parity.values()):
        raise ValueError(f"Saved North publication parity differs: {parity}")


if __name__ == "__main__":
    worker(Path(sys.argv[1]), Path(sys.argv[2]).resolve(strict=True) / "reports/ALGO08/v3")
