"""Verify scientific and rendering equality after all fresh and forked children exit."""

from hashlib import sha256
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from preloaded_saved_worker import PLAN, read, write


def require_parity(observed, control):
    if observed != control:
        changed = [key for key in observed if observed.get(key) != control.get(key)]
        raise ValueError(f"Isolated saved publication differs at {', '.join(changed)}")


def science(root, receipt, job, identity):
    from joint_publication import artifacts
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification.paired_publication import evidence

    data = evidence(root, receipt, job["started_unix_ns"], read_only=True)
    verified = artifacts(root, receipt)
    trace = read(root / "joint-research-receipt.json")
    (packet,) = root.glob("fast-scan-automatic-work/*/detections.json")
    grid_store = FastStandardAnalysisStore(root)
    run = receipt["run_id"]
    terminal = read(root / "fast-scan-automatic-work" / run / "terminal.json")
    path, grid = grid_store.position_path(run), grid_store.position_grid(run)
    images = verified["images"]
    offer = Algo08Region.parse(identity["original_offer"]).document()
    checks = dict(complete=receipt["decision"] == "complete" and data["reason"] is None,
                  offer=receipt["region"] == offer, session=receipt["session_id"] == identity["session"],
                  issued=receipt["window_count"] == identity["issued"], authority=data["raw_authority"] == identity["authority"],
                  native=terminal["native_sha256"] == identity["native_sha256"] == "sha256:"+sha256(packet.read_bytes()).hexdigest(),
                  cutoff=read(packet)["clock_anchor"]["before"]["realtime_ns"] == identity["cutoff_utc_ns"],
                  grid=grid["complete"] and grid["matched_c_grid"],
                  figures=len(images) == 8 and all(row["binding"]["position_png_sha256"] == images["position"]["sha256"]
                                                  for row in (path, grid)),
                  bindings=all(row["binding"]["input_sha256"] == identity["native_sha256"]
                               and row["binding"]["terminal_sha256"] == receipt["terminal_sha256"]
                               and row["binding"]["owner_sha256"] == data["owners"] for row in (path, grid)))
    failed = [field for field, valid in checks.items() if not valid]
    if failed:
        raise ValueError(f"{root} lacks bound saved evidence for {', '.join(failed)}")
    roles = trace["selected_rows"]
    if set(roles) != {"c0", "fitted_c"} or any(canonical_digest({r[0]: r[1] for r in rows}) != data["owners"][key]
                                             for key, rows in roles.items()):
        raise ValueError("Ordered owner rosters do not bind the actual calibration arms")
    return dict(identity=identity, terminal=receipt["terminal_sha256"], arms=data["arms"], roles=roles,
                grid_and_path=data["scientific_digests"], grid_points=grid["evaluated_points"], images=images,
                named_finish=trace["route_details"]["named_survivor_fit"]["status"])


def score(root):
    from empty_bootstrap import checked

    binding = read(root / "binding.json")
    for name, digest in binding["sources"].items():
        path = HERE / name
        if path == Path(__file__).resolve():
            checkout = HERE.parents[2]
            version = subprocess.check_output(["git", "-c", f"safe.directory={checkout}", "-C", str(checkout),
                                              "show", f"{binding['commit']}:{path.relative_to(checkout)}"])
            if sha256(version).hexdigest() != digest:
                raise ValueError("The original post-exit verifier is unbound")
        else:
            checked(path, digest)
    runs, controls = {}, {}
    for ordinal, (mode, order) in enumerate(PLAN, 1):
        label = f"{ordinal}-{mode}"
        directory = root / label
        timed = read(root / (label+"-clock.json"))
        sequence = read(directory / "sequence.json")
        jobs = sequence["jobs"]
        if (timed["clock"]["exit_code"] or [job["case"] for job in jobs] != list(order)
                or len({job["pid"] for job in jobs}) != len(order)
                or any(job["status"] or job["pid"] == sequence["initialized"]["pid"] for job in jobs)):
            raise ValueError("Both isolated children must publish one original sequence")
        for job in jobs:
            case = job["case"]
            published = read(directory / case / "request-receipt.json")
            if published["waveform_calls"] or published["handoffs"] != 1 or published["preloaded"] != (mode == "preloaded"):
                raise ValueError("Each signed saved request needs exactly one isolated native handoff")
            actual = science(directory / case, published["receipt"], job, published["request"])
            if case in controls:
                require_parity(actual, controls[case])
            else:
                controls[case] = actual
            job["publication"] = {key: published[key] for key in ("solve", "internal_request")}
        runs[label] = dict(timed=timed, sequence=sequence)
    if len({control["identity"]["inventory"] for control in controls.values()}) != len(controls):
        raise ValueError("The same process needs independent original input and offers")
    write(root / "score.json", dict(binding_sha256=sha256((root/"binding.json").read_bytes()).hexdigest(),
          runs=runs, science=controls, parity=True, verifier_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    score(Path(sys.argv[1]))
