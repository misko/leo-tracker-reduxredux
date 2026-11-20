"""Run one private pilot admission and compact solve under the measured cap."""

import json
import os
import resource
import sys
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time


def execute(bundle, authority_file, arm, cpu, unit):
    from tools.pipeline_eval.variants.pilot_distill import Rule, apply_winners, strongest
    from tools.pipeline_eval.variants.v5_direct_cavity import run

    entry = next(
        line[3:]
        for line in Path("/proc/self/cgroup").read_text().splitlines()
        if line.startswith("0::")
    )
    group = Path("/sys/fs/cgroup") / entry.lstrip("/")
    if (
        group.name != unit + ".service"
        or int((group / "memory.max").read_text()) != 512 * 2**20
        or int((group / "memory.swap.max").read_text()) != 0
        or os.sched_getaffinity(0) != {cpu}
        or os.nice(0) < 10
    ):
        raise ValueError("compact pilot worker left its service limits")
    authority = json.loads(authority_file.read_bytes())
    native = Path(authority["fast"]["local"])
    digest = authority["fast"]["native_sha256"]
    gate_started, gate_cpu = perf_counter(), process_time()
    encoded = native.read_bytes()
    if sha256(encoded).hexdigest() != digest:
        raise ValueError("fast factors have changed")
    accepted = authority["counts"][arm]
    if arm != "stock":
        document = json.loads(encoded)
        probes = [probe["candidates"] for probe in document["source"]["probes"]]
        if arm == "learned":
            model = Path(authority["rule"]["path"]).read_bytes()
            if sha256(model).hexdigest() != authority["rule"]["sha256"]:
                raise ValueError("the held worker did not receive the frozen model")
            rule = Rule(**json.loads(model)["rule"])
            rate = document["source"]["sample_rate_hz"]
            chosen = {
                i: winner
                for i, candidates in enumerate(probes)
                if (winner := rule.select(candidates, round(rate / 750), rate * 0.2e-6)) is not None
            }
        elif arm == "strength":
            chosen = strongest(probes, accepted)
        elif arm == "oracle":
            chosen = dict(authority["oracle_members"])
        else:
            raise ValueError("unknown pilot evaluation arm")
        selected_sha = sha256(json.dumps(sorted(chosen.items())).encode()).hexdigest()
        if len(chosen) != accepted or selected_sha != authority["selection_sha256"][arm]:
            raise ValueError("worker selected different admissions than the frozen inputs")
        transformed = apply_winners(document, chosen)
        encoded = (json.dumps(transformed, sort_keys=True, separators=(",", ":")) + "\n").encode()
        native = Path.cwd() / "admitted-native.json"
        native.write_bytes(encoded)
        digest = sha256(encoded).hexdigest()
        del document, transformed, probes, chosen
    del encoded
    policy = dict(wall_s=perf_counter() - gate_started, cpu_s=process_time() - gate_cpu)
    fit_started, fit_cpu = perf_counter(), process_time()
    result = run(
        native=native,
        native_sha256=digest,
        track_config=authority["track_config"],
        config_sha256=authority["track_config_sha256"],
        session=authority["session"],
        archive=authority["archive"],
        native_backend=bundle / "native/manifest.json",
        library=bundle / "projector.so",
        tile=authority["tile"]["center"],
        screen_center=authority["screen_center"],
        width_km=authority["tile"]["width_km"],
    )
    position = dict(wall_s=perf_counter() - fit_started, cpu_s=process_time() - fit_cpu)
    if any(
        not Path(m.__file__).resolve().is_relative_to(bundle)
        for n, m in sys.modules.items()
        if n.partition(".")[0] in {"leo", "tools"} and getattr(m, "__file__", None)
    ):
        raise ValueError("project code escaped the installed receiver")
    return dict(
        result=result,
        native_sha256=digest,
        admitted_probes=accepted,
        policy=policy,
        position=position,
        resources={
            name: int((group / name).read_text())
            for name in ("memory.max", "memory.peak", "memory.swap.current")
        }
        | {"rss_peak_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},
    )


if __name__ == "__main__":
    bundle, authority = (Path(value).resolve() for value in sys.argv[1:3])
    sys.path.insert(0, str(bundle))
    result = execute(bundle, authority, sys.argv[3], int(sys.argv[4]), sys.argv[5])
    print(json.dumps(result, allow_nan=False))
