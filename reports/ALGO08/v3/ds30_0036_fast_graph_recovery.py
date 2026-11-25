"""Resume the one approved corrected 0036 cell after verified import-path setup failure."""

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
from shutil import copytree
import sys
from types import ModuleType
from unittest.mock import patch

WORKER = Path(__file__).resolve()
HERE = WORKER.parent
sys.path.insert(0, str(HERE))

import ds30_next_moment_publication as entry  # noqa: E402
from ds30_next_moment_publication import capsule, elapsed, fast, moment, replay, saved, started, transfer  # noqa: E402


AMENDMENT = "ds30-0036-fast-graph-recovery.md"
AMENDMENT_PIN = "9deda18bff1335dca46e78c0a5bc8dfa293797879330176e0d2461579c1e1829"
FAILED = "measurements/ds30-0036-fast-graph-first-failure.json"
FAILED_PIN = "aa729713077e0fd66edfecdd0f14ac754d97328e2cd9de1388e6a31967446ff8"
ORIGINAL = Path("/tmp/leo-ds30-next-moment-saved01")
GRAPH_HELPERS = {
    fast.PORT: fast.PORT_PIN,
    "vector_graph_edges.py": "b4a4c67f9100b668129bce2c4baa23440edde92374386260475be01f898115fd",
    "polynomial_fit_cache.py": "6c2f936f9904c707a6dab7846fb242602baf72a369c1c207624825625906c75b",
}
ENTRY_EXPERIMENT, ENTRY_CORRECTION, ENTRY_CHILD = entry.experiment, entry.correction, entry.isolated_child


@contextmanager
def reviewed_helpers():
    from empty_bootstrap import checked

    previous = {Path(filename).stem:sys.modules.get(Path(filename).stem) for filename in GRAPH_HELPERS}
    prior_paths = {name:getattr(module, "__file__", None) for name,module in previous.items()}
    try:
        for filename,pin in GRAPH_HELPERS.items():
            path = HERE/filename
            body = checked(path, pin)
            module = ModuleType(path.stem)
            module.__file__ = str(path)
            sys.modules[module.__name__] = module
            exec(compile(body, str(path), "exec"), module.__dict__)
        yield prior_paths
    finally:
        for name,module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


@contextmanager
def correction(mode):
    with ENTRY_CORRECTION(mode):
        if mode == "ordinary":
            yield
            return
        operation = moment.formed_features

        def formed(native, config, feature, ordinary_graph, report):
            with reviewed_helpers() as previous:
                result = operation(native, config, feature, ordinary_graph, report)
            report["reviewed_graph_imports"] = dict(previous_bindings=previous, verified_local=GRAPH_HELPERS,
                                                   bindings_restored=True)
            return result

        with patch.object(moment, "formed_features", formed):
            yield


def experiment(*, probe):
    spec = ENTRY_EXPERIMENT(probe=probe)
    spec.source = WORKER.name
    spec.transfer_sources += ("ds30_next_moment_publication.py", AMENDMENT, FAILED)
    return spec


def activation(cell, pin):
    from empty_bootstrap import RELEASE
    from leo.analysis.localization_v3 import tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from masked_cfo_saved import CONFIG_PIN, FEATURE_PIN
    from reports.ALGO08.v3 import held_cfo_features as feature

    if saved.identifier(Path(feature.__file__)) != FEATURE_PIN:
        raise ValueError("No-solve activation requires the frozen feature source")
    plan = saved.document(cell/"plan.json", pin)
    native = saved.document(cell/"derived-native.json", plan["original_native_sha256"])
    config = TrackConfig(**saved.document(RELEASE/"assets/tracks.json", CONFIG_PIN)["config"])
    report = {}
    start = started()
    with correction("corrected"):
        moment.formed_features(native, config, feature, tracks.prepare_tracks, report)
    scope = report["fast_graph_formation"]
    flags = {name: count["native_paths"]["native_paths"] > 0 and count["graph"]["calls"] == 1
             for name,count in scope["scopes"].items()}
    if flags != {"held_odd_mask":True,"ordinary":True} or not report["projection"]["moments_valid"]:
        raise ValueError("The actual signed no-solve activation did not exercise both exact Graphs")
    return saved.write(cell/"fast-graph-activation.json", dict(mode=scope["method"], activated=flags,
        imports=report["reviewed_graph_imports"], source_pins=scope["sources"], plan_sha256=pin,
        projection_proof_valid=True, native_sha256=plan["original_native_sha256"], clock=elapsed(start),
        solver_calls=0, waveform_reads=0))


def child(cell, pin, mode, *, probe_only):
    ENTRY_CHILD(cell, pin, mode, probe_only=probe_only)
    if mode == "corrected" and probe_only:
        activation(cell, pin)


def rebind(run):
    if run.exists() or run.parent != Path("/tmp") or run.resolve() != run:
        raise ValueError("Require a fresh direct /tmp recovery root")
    if saved.identifier(HERE/AMENDMENT) != AMENDMENT_PIN:
        raise ValueError("The approved corrected-only recovery protocol changed")
    failure = saved.document(HERE/FAILED, FAILED_PIN)
    prior = saved.document(ORIGINAL/"next-moment-ready.json",failure["prior_ready_sha256"])
    old = ORIGINAL/"field"
    rejected = old/"corrected"
    if (prior["row"]["case"] != failure["case"]
            or not all(saved.identifier(rejected/name)==pin for name,pin in failure["failure_pins"].items())
            or (rejected/"receipt.json").exists() or any((rejected/"substituted").rglob("terminal.json"))):
        raise ValueError("The original sealed no-fit, no-terminal failure changed")
    gate_pin = failure["ordinary_gate_sha256"]
    gate = saved.document(old/"ordinary-gate.json",gate_pin)
    if not saved.document(old/"ordinary-parity.json",gate["parity"])["exact_ordinary_scientific_parity"]:
        raise ValueError("Require the existing official ordinary scientific parity")
    beginning = started()
    root, stage = run/"field", run/"field/stage"
    root.mkdir(mode=0o700, parents=True)
    transfer.mount_root(run).mkdir(mode=0o700)
    copytree(old/"stage", stage, copy_function=os.link, symlinks=True)
    copytree(old/"ordinary", root/"ordinary", copy_function=os.link, symlinks=True)
    for name in ("ordinary-gate.json", "ordinary-parity.json"):
        os.link(old/name, root/name)
    cell = root/"corrected"
    cell.mkdir(mode=0o700)
    for name in ("admission.json","derived-native.json"):
        os.link(rejected/name,cell/name)
    before = saved.document(rejected/"plan.json",prior["plans"]["corrected"])
    plan = saved.write(cell/"plan.json", dict(before, stage=str(stage), sources=saved.source_pins(experiment(probe=False))))
    binding = elapsed(beginning)
    preflight = started()
    with entry.ports(run, prior["row"]):
        ready = capsule.preflight(cell,plan,"corrected",replay.OBSERVER_PIN)
    proof = saved.document(cell/"fast-graph-activation.json")
    if proof["plan_sha256"] != plan or any(proof[key] for key in ("solver_calls","waveform_reads")):
        raise ValueError("Require the exact actual no-solve activation receipt")
    recovery = dict(protocol_sha256=AMENDMENT_PIN, prior_refusal_sha256=FAILED_PIN, original_ordinary_gate_sha256=gate_pin,
        binding_clock=binding, new_archive_bytes=0,new_saved_json_storage_reads=0,
        preflight_clock=elapsed(preflight), activation_sha256=saved.identifier(cell/"fast-graph-activation.json"))
    return saved.write(run/"next-moment-ready.json", dict(prior, plans=dict(prior["plans"],corrected=plan),
        readiness=dict(prior["readiness"],corrected=ready), recovery=recovery))


def main():
    with patch.multiple(entry, WORKER=WORKER, experiment=experiment, correction=correction, isolated_child=child):
        if sys.argv[1:2] == ["rebind"]:
            parser = argparse.ArgumentParser(description=__doc__)
            parser.add_argument("mode", choices=("rebind",))
            parser.add_argument("root", type=Path)
            sys.addaudithook(saved.deny_backing)
            print(rebind(parser.parse_args().root))
            return 0
        return entry.main()


if __name__ == "__main__":
    raise SystemExit(main())
