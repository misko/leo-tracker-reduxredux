"""Stage-only signed fit diagnostic on sealed saved receiver handoffs."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SPLITS = {"development": ("0016", "0316"), "held": ("0008", "0402"), "held-0402-recovery": ("0402",)}
STAGED = {
    "0016": ("leo-v3-portable-repaired-0016-containing-01/ordinary/binding.json",
             "6883cb60e777fcb223862c765d2e4f1cc1a579fa126704f71c64be06c3368f82"),
    "0316": ("leo-v3-final-0316-transfer-result02/request.json",
             "c9be0ae39a59a69621f9b9a6f4062ea7e33d1ba1de05c394771001f1b26ce4b3"),
    "0008": ("leo-v3-mixed-final-0008-01/binding.json",
             "71bb3459952cf21760764690f54e6536c154151257ba2cf854b1fa11b29870a5"),
    "0402": ("leo-v3-saved-0402-pair-01/request.json",
             "a2d730f64833eafd096877650e24b5c250b3bcfbef69d6bb5a44b70f0cbf1274"),
}
SAVED_SOURCE_UPDATES = {
    "unified_short_bootstrap.py": "d2c4d213008ce2f1ca3ce29d2d755eeb9fb1b5c0fcef603bbc0f87cf688c3c27",
    "joint_publication.py": "3431764b4c6f888c4addb6b788f6e9f1715a76e1500fc047cb875959d0c24e01",
}


class ProbeComplete(Exception):
    """Exit before standard evidence or publication after the measured fit port."""


@contextmanager
def record_handoff(audit):
    from unified_short_bootstrap import Handoff

    original = Handoff.install

    @contextmanager
    def active(handoff, scan):
        try:
            with original(handoff, scan):
                yield
        finally:
            audit.append((handoff.calls, handoff.session, handoff.inventory, handoff.receiver))

    with patch.object(Handoff, "install", active):
        yield


def run_case(case, root, request):
    if case == "0016":
        from portable_omitted_region import worker

        worker(root, "ordinary", "on")
    elif case == "0316":
        from named_final_0316 import run_worker

        run_worker(request, root / "published")
    elif case == "0008":
        from cumulative_grid_projection import worker

        worker(request, "combined", root / "published", named_survivor_finish=True)
    elif case == "0402":
        import isolated_salvage_0402_trial as isolated
        import prospective_0402_solver as prior
        from named_survivor_0402_trial import fixed_worker

        with (patch.object(isolated, "POLICY_PINS", isolated.POLICY_PINS | SAVED_SOURCE_UPDATES),
              patch.object(prior, "PINS", prior.PINS | SAVED_SOURCE_UPDATES)):
            fixed_worker(root / "published")
    else:
        raise ValueError("Unenrolled saved diagnostic")


def worker(case, root):
    from empty_bootstrap import checked
    from named_survivor_fit import fit_record
    import named_survivor_fit
    from survivor_sensitivity import pair

    name, pin = STAGED[case]
    raw = checked(Path("/dev/shm") / name, pin)
    request = root / "binding.json"
    if case == "0316":
        data = json.loads(raw)
        data["source_pins"].update(SAVED_SOURCE_UPDATES)
        raw = json.dumps(data).encode()
    request.write_bytes(raw)
    result, handoffs = {}, []

    def observe(candidate, means, audit, witness):
        from blind_joint_signed import describe

        results = pair(candidate, means, result)
        result["fits"] = {a: fit_record(fit) for a, fit in results.items()}
        roster = describe(candidate)
        result["curved"] = roster["curved"]
        result["predictive"] = roster["predictive"]
        raise ProbeComplete

    with record_handoff(handoffs), patch.object(named_survivor_fit, "fit_pair", observe):
        try:
            run_case(case, root, request)
        except ProbeComplete:
            pass
        else:
            raise ValueError("The live qualified named-survivor fit port was bypassed")
    if len(handoffs) != 1 or handoffs[0][0] != 1 or list(root.rglob("terminal.json")):
        raise ValueError("Expected exactly one saved handoff and no stock or research publication")
    from aperture_trial import write

    write(root / "probe.json", dict(case=case, staged_request_sha256=pin, handoff=handoffs[0],
                                  waveform_calls=0, **result))


def launch(split, root, *, worker_path=None, extra_sources=()):
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    if root.resolve().parent != Path("/dev/shm"):
        raise ValueError("Use a new direct tmpfs output directory")
    machine = host()
    root.mkdir(mode=0o700)
    (root / "tmp").mkdir()
    cases = SPLITS[split]
    sources = ("survivor_sensitivity_trial.py", "survivor_sensitivity.py", "survivor-sensitivity-protocol.md",
               "lighter_joint_estimator.py", "named_survivor_fit.py", "blind_joint_signed.py", "isolated_salvage.py",
               "unified_short_bootstrap.py", "joint_publication.py", *extra_sources)
    write(root / "binding.json", dict(machine=machine, cases=cases, split=split,
                  source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in sources}))
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    clocks = {}
    for case in cases:
        target = root / case
        target.mkdir()
        command = ["/usr/bin/timeout", "--kill-after=2s", "50s", RELEASE / "venv/bin/python", "-IB", worker_path or __file__,
                   "worker", case, target]
        clock = measure(command, env, target)
        write(root / f"{case}-clock.json", clock)
        clocks[case] = clock
    write(root / "feature-seal.json", {case: sha256((root / case / "probe.json").read_bytes()).hexdigest()
                                     for case in cases if clocks[case]["exit_code"] == 0})
    if any(clock["exit_code"] != 0 for clock in clocks.values()):
        raise ValueError("Saved diagnostic failed; standalone worker clocks and successful features are sealed")


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker"))
    parser.add_argument("name")
    parser.add_argument("root", type=Path)
    options = parser.parse_args()
    globals()[options.action](options.name, options.root)
