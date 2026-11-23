"""Transfer the frozen fixed-epoch CFO rule to one signed, resident North member."""

import argparse
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from tools.pipeline_eval.qualification.cache_residency import load_query

from . import short_cfo_refine as trial
from . import tail_confirm as previous

FREEZE = "efd70c2ee3739320067788d6feb7c7b6c77a8ee29285c2a61b4787eb28c34951"
DSO = "fed887f464c78d9a547bd1d939dbb0a3987ab4babd3db8f0779928be5a6a1d4e"


def run(destination, library, freeze_path):
    machine = trial.check_machine()
    freeze = trial.load(freeze_path, FREEZE)
    if (
        freeze["driver_sha256"] != trial.file_sha(Path(trial.__file__))
        or freeze["extension_sha256"] != trial.file_sha(Path(trial.__file__).with_suffix(".inc"))
        or trial.file_sha(library) != DSO
    ):
        raise ValueError("North transfer requires the unchanged held physical implementation")
    previous.verified(previous.CACHE_LIBRARY, previous.CACHE_SHA)
    query = load_query(previous.CACHE_LIBRARY)
    io, start = trial.input_bytes(), trial.clock()
    clips, scope = previous.north_panel(query)
    intake = trial.since(start)
    if trial.input_bytes() != io:
        raise ValueError("North fixture was not already resident")
    rows = [
        dict(
            key=row["key"],
            lane=lane,
            edge=row["w"].target["edge"],
            mode=row["mode"],
            iq=iq,
            tune=trial.center(row["w"]),
            stock=row["named"][lane],
            short=row["sealed"][lane],
        )
        for row, iq in clips
        for lane in (0, 1)
    ]
    with ExitStack() as stack:
        native = {}
        for edge, pin in trial.PILOT_SHA.items():
            asset = np.frombuffer(
                trial.verified(trial.RELEASE / "assets" / f"{edge}.f32", pin), dtype="<f4"
            )
            for name, library_path, sha in (
                ("full", trial.PAYLOAD / "receiver.so", trial.INSTALLED_SHA),
                ("short_primary", trial.ORIGINAL / "short-primary.so", trial.PREFIX_PIN),
            ):
                trial.verified(library_path, sha)
                path = trial.NativePath(library_path, asset, name)
                native[edge, name] = path
                stack.callback(path.close)
        result = trial.measure(rows, trial.Refine(library), native, (freeze["step"],))
    stats = trial.summary(result["rows"], freeze["step"])
    radios = {
        str(radio): trial.summary([r for r in result["rows"] if r["lane"] == radio], freeze["step"])
        for radio in (0, 1)
    }
    trial.save(
        destination,
        result
        | dict(
            input=scope,
            intake_ns=intake,
            cpu=machine,
            freeze_sha256=FREEZE,
            library_sha256=DSO,
            source_sha256=trial.file_sha(Path(__file__)),
            summary=stats,
            radios=radios,
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("destination", "library", "freeze_path"):
        cli.add_argument(name, type=Path)
    run(**vars(cli.parse_args()))
