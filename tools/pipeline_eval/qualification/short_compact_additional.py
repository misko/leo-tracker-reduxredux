"""Move only unstarted short-compact cases onto the released CPU lanes."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import short_compact as trial
from .full_v5_check import _sha

ASSIGNMENT = "additional-cpus.json"


def assignments(plan):
    proposed = [case for case in plan["cases"] if plan["cases"][case]["profile"] == "waveform"]
    return {
        "2": [proposed[0]],
        "3": [proposed[1]],
        "20": [proposed[2]],
    }


def waveform_scopes(doc):
    source = doc["source"]
    span = source["sample_rate_hz"] * source["probe_ms"] // 1000
    ends = [p["valid_start_counter"] + span for p in source["probes"]]
    ends.extend(row["sample_end"] for row in doc["provenance"]["excluded_windows"])
    final_visit = max(ends)
    idle = doc["last_sample_counter"] - final_visit
    if not 0 <= idle <= 5 * source["sample_rate_hz"]:
        raise ValueError("planned waveform end has no bounded idle tail")
    # The original full document, including its declared terminal counter, still
    # reaches the full solver. The slice inventory ends at the final actual visit.
    return trial.scopes(dict(doc, last_sample_counter=final_visit))


def extend(base):
    source = trial.REPORT / "source-lock.json"
    lock = whole_iq.read(
        whole_iq.checked(source, (base / "source-lock.sha256").read_text().strip())
    )
    for name, sha in lock["sources"].items():
        whole_iq.checked(ROOT / name, sha)
    new = assignments(lock)
    additional = base / "additional"
    additional.mkdir(exist_ok=True)
    filed = trial.REPORT / ASSIGNMENT
    if whole_iq.read(whole_iq.checked(filed, _sha(additional / ASSIGNMENT)))["cpus"] != new or any(
        (additional / ident / "0").exists() for ids in new.values() for ident in ids
    ):
        raise ValueError("the preflight correction cannot change or replay the assigned roster")
    save_json(
        trial.REPORT / "waveform-adapter-lock.json",
        dict(
            original_assignment_sha256=_sha(filed),
            adapter_sha256=_sha(Path(__file__)),
            detail="Authenticate the 1.672 s idle tail without changing the original full file.",
        ),
    )
    receiver = Path(lock["receiver"])
    if whole_iq.receiver_identity(receiver) != lock["receiver_files"]:
        raise ValueError("phase-release source changed before the appended schedule")

    def lane(item):
        cpu, ids = item
        for ident in ids:
            spec = lock["cases"][ident]
            native = whole_iq.checked(Path(spec["native"]), spec["native_sha256"])
            whole_iq.checked(Path(spec["track_config"]), spec["config_sha256"])
            archives = {p.name: _sha(p) for p in Path(spec["archive"]).rglob("*.tle")}
            if archives != {
                name: pin.removeprefix("sha256:") for name, pin in spec["snapshots"].items()
            }:
                raise ValueError("appended replay is missing a frozen causal snapshot")
            document = whole_iq.read(native)
            visits = waveform_scopes(document)
            for name in ("0", "1", "2", "full"):
                trial.run_method(
                    additional, spec, document, visits, receiver, int(cpu), name, lock["limits_s"]
                )

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lane, new.items()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=local_output)
    extend(parser.parse_args().base)
