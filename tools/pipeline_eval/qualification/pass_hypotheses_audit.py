"""Replay only the independent pass geometry diagnostic from a sealed run."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..__main__ import ROOT, encoded, save_json
from ..variants import pass_hypotheses_audit as model
from . import pass_hypotheses_trial as trial

OUT, world = trial.OUT, trial.world
WORKER = trial.WORKER.replace(
    "import pass_hypotheses as solver", "import pass_hypotheses_audit as solver"
)


def run():
    seal = world.read(OUT / "prediction-lock.json")
    world.verify(OUT, seal["files"])
    plan = world.read(OUT / "blind-plan.json")
    jobs = plan["cases"]
    offers, wave = trial.previous.waveform()
    if offers != [q for q in jobs if q["cohort"] == "waveform"]:
        raise ValueError("diagnostic waveform offers differ from the frozen science")
    source = [Path(__file__), Path(model.__file__), OUT / "CONDITIONING-PROTOCOL.md"]
    hashes = {str(p.relative_to(ROOT)): world.digest(p.read_bytes()) for p in source}
    save_json(OUT / "audit-source-lock.json", hashes)

    def lane(i):
        cpu = trial.CPUS[i]
        out = []
        for q in jobs[i::2]:
            snapshot = wave if q["cohort"] == "waveform" else world.clock.data(q, None)
            request = encoded(dict(capture=snapshot, tile=q["tile"]))
            prior = world.prior
            argv = prior.command(cpu, "peak_paths", prior.sources()["peak_paths"][0])
            argv[-1] = WORKER
            world.clock.ablation._mount(
                argv,
                [
                    Path(model.__file__),
                    Path(trial.model.__file__),
                    Path(trial.model.native.__file__),
                    Path(world.model.geodesy.__file__),
                    *world.clock.candidate_sources(),
                ],
            )
            p = subprocess.run(argv, input=request, capture_output=True, check=True, timeout=45)
            r = json.loads(p.stdout)
            out.append(dict(id=q["id"], cpu=cpu, input_sha256=world.digest(request), **r))
        return out

    with ThreadPoolExecutor(2) as pool:
        rows = [r for group in pool.map(lane, range(2)) for r in group]
    if any(world.digest((ROOT / k).read_bytes()) != v for k, v in hashes.items()):
        raise ValueError("diagnostic tools changed between seal and run")
    save_json(
        OUT / "conditioning.json",
        dict(
            rows=rows,
            original_prediction_lock_sha256=world.digest(
                (OUT / "prediction-lock.json").read_bytes()
            ),
        ),
    )
    files = {
        k: world.digest((OUT / k).read_bytes())
        for k in ("audit-source-lock.json", "conditioning.json", "CONDITIONING-PROTOCOL.md")
    }
    save_json(OUT / "conditioning-lock.json", dict(files=files, cases=seal["cases"]))


if __name__ == "__main__":
    run()
