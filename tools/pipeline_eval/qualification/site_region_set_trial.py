"""Freeze public placements and run isolated receiver region competitions."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.io import loadmat

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..__main__ import ROOT, encoded, save_json
from ..reference import grid
from ..variants import beacon_transfer as shape
from ..variants import site_region_set as model
from ..variants.bearing_transfer import RF
from . import bearing_transfer_trial as prior
from .armijo_finish_results import pack
from .fresh_scenes import _destination
from .physical_differences import consolidate, simultaneous

OUT = ROOT / "reports/2026_11_19_receiver_screening/native-receiver/site-region-sets"
STUDY = prior.authority.STUDY
CPUS = (22, 23)
CAP = 35
METHODS = ("site_region_set", "frozen_regional")
ARCHIVE = "blind-predictions.jsonl.gz"
PROTOCOL = "site-region-set-20261120-spherical"
EARTH_RADIUS_KM = 6371.0088
C_DELTA = 100_000.0
SIM_ORIGIN = (38.900, -9.310)
SIM_TRUTH = (38.840, -9.230)
WORKER = """
import json
import sys
from time import perf_counter, process_time
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit

start, cpu = perf_counter(), process_time()
setrlimit(RLIMIT_AS, (640 << 20, 640 << 20))
method, = sys.argv[1:]
q = json.load(sys.stdin)
if set(q) != {'observation', 'catalogue', 'offers'}:
    raise ValueError('unexpected anonymous packet fields')
if method == 'frozen_regional':
    from engine.receiver import solve
    obs = q['observation']
    observation = obs['clock'] | {'tracks': [
        dict(times=a['time'], values=a['frequency'], rf_hz=11325000000, receiver=0, channel=0)
        for a in obs['arcs']
    ]}
    result = solve(observation, q['offers'], q['catalogue'])
else:
    from tools.pipeline_eval.variants.site_region_set import solve
    result = solve(**q)
json.dump(dict(status='done', raw=result, cpu_s=process_time()-cpu,
               worker_wall_s=perf_counter()-start, rss_kib=getrusage(RUSAGE_SELF).ru_maxrss),
          sys.stdout, allow_nan=False)
"""


def digest(raw):
    return sha256(raw).hexdigest()


def token(*parts):
    return digest("/".join(map(str, (PROTOCOL, *parts))).encode())


def rng(*parts):
    return np.random.default_rng(int(token(*parts)[:16], 16))


def panels(origin, identity, number):
    random = rng(identity, number, "placement")
    angle = random.uniform(0, np.pi * 2)
    jitter = random.uniform(0.6, 2)
    displaced = _destination(origin, jitter, random.uniform(0, np.pi * 2))
    far = number == 2
    step = (
        random.uniform(59, 76)
        if far
        else random.uniform(27, 31)
        / max(abs(np.sin(angle + np.pi / 4)), abs(np.cos(angle + np.pi / 4)))
    )
    radial_km = step / np.sqrt(2)
    radius = radial_km / EARTH_RADIUS_KM
    centre = _destination(displaced, radial_km, angle)
    radial = ecef_to_enu_matrix(*centre)[2]
    anchor = ecef_to_enu_matrix(*displaced)[2]
    start = anchor - radial * (anchor @ radial)
    start /= np.linalg.norm(start)
    cross = np.cross(radial, start)
    square = [
        radial * np.cos(radius) + offset * np.sin(radius)
        for offset in (start, cross, -start, -cross)
    ]
    edge = int(random.integers(1, 3))
    normal = np.cross(square[edge], square[edge + 1])
    normal /= np.linalg.norm(normal)

    def offer(vertex, unit):
        latitude = np.arctan2(unit[2], np.hypot(*unit[:2]))
        longitude = np.arctan2(unit[1], unit[0])
        return dict(
            id=token(identity, number, vertex, "tile")[:20],
            center=np.rad2deg([latitude, longitude]).tolist(),
        )

    primary = [offer(i, unit) for i, unit in enumerate(square)]
    reflected = [
        primary[i] if i in (edge, edge + 1) else offer(i + 4, u - 2 * (u @ normal) * normal)
        for i, u in enumerate(square)
    ]
    for slide in (False, True):
        offers = reflected if slide else primary
        order = rng(identity, number, slide, "order").permutation(len(offers))
        yield dict(
            id=token(identity, number, slide, "case")[:20],
            trial=number,
            tier="far" if far else "near",
            slide=slide,
            offers=[offers[i] for i in order],
        )


def anonymous_arcs(rows):
    tracks = [consolidate(row) for row in rows]
    _, pairs = simultaneous(tracks)
    duplicate = {
        min(p["track_rows"], key=lambda i: (np.ptp(tracks[i][0]), -i))
        for p in pairs
        if p["harmonic_like"]
    }
    return [
        dict(arc=i, time=t.tolist(), frequency=f.tolist())
        for i, arc in enumerate(tracks)
        if i not in duplicate and (sample := shape.sampled(*arc)) is not None
        for t, f in [sample]
    ]


def recordings(raw):
    for folder in (prior.OUT, OUT.parents[1] / "original-schedule/beacon-transfer"):
        for name, expected in prior.read(folder / "prediction-lock.json")["files"].items():
            prior.authority._read(folder / name, expected)
    public = STUDY / "public_field"
    receipt = prior.read(STUDY / "field-receipt.json")
    plan = prior.read(prior.OUT / "blind-plan.json")["cases"]
    captures = prior.read(prior.OUT / "measurement-inventory.json")["captures"]
    prior_sources = {p["id"]: p for p in plan if not p["author_id"] and p["mode"] == "containing"}
    for item in captures:
        if item["repeated_site"]:
            continue
        original = prior_sources[item["id"] + "-containing"]
        ident = original["original_case_id"]
        q = json.loads(
            prior.authority._read(
                public / "queries" / f"{ident}.json", receipt["public_query_sha256"][ident]
            )
        )
        obs = json.loads(
            prior.authority._read(
                public / "observations" / f"{q['observation']}.json", q["observation"]
            )
        )
        cat = prior.authority._read(public / "orbits" / f"{q['catalog']}.tle", q["catalog"])
        native_path = raw / item["date"] / "tracked_tones.mat"
        native = prior.authority._read(native_path, item["native_sha256"])
        mat = loadmat(BytesIO(native), variable_names=["main_tone_dict"])
        arcs = anonymous_arcs(mat["main_tone_dict"].ravel())
        clock = {
            k: obs[k]
            for k in ("anchor_utc_ns", "cutoff_utc_ns", "catalog_timestamp_ns", "duration_s")
        }
        binding = dict(
            site=item["site"],
            original_case=ident,
            recording=item["id"],
            native_file=str(native_path),
            native_sha256=item["native_sha256"],
            catalogue_sha256=q["catalog"],
            observation_source_sha256=q["observation"],
            origin=original["tile"]["center"],
            sample_count=sum(len(a["time"]) for a in arcs),
            arcs=len(arcs),
            cohort="physical",
        )
        if not any(r["center"] == binding["origin"] for r in q["regions"]):
            raise ValueError("public placement mismatches the sealed inventory")
        yield binding, dict(clock=clock, arcs=arcs), cat.decode("ascii")


def simulation(clock, catalogue):
    sky = grid.prepare_sky(clock, catalogue)
    frame = ecef_to_enu_matrix(*SIM_TRUTH)
    xyz = geodetic_to_ecef_km(*SIM_TRUTH, 0.05)
    random = rng("simulation", "noise")
    kind = np.arange(sky.positions_km.shape[1]) * grid.COARSE_ORBIT_STEP_S - grid.PHASE_LIMIT_S
    available, arcs = set(range(len(sky.satellites))), []
    for start in range(48, 790, 74):
        time = np.arange(start + 0.31, start + 71, 1.0)
        nearest = np.argmin(abs(kind - np.median(time)))
        rays = sky.positions_km[:, nearest] - xyz
        height = (rays @ frame[2]) / np.linalg.norm(rays, axis=1)
        ranked = [i for i in np.argsort(-height) if i in available][:24]
        sats = tuple(sky.satellites[i] for i in ranked)
        sats, p, v = grid._valid_states(sats, sky.anchor_utc_ns, time)
        delta = p - xyz
        rays = delta / np.linalg.norm(delta, axis=-1, keepdims=True)
        minimum = (rays @ frame[2]).min(axis=1)
        if not len(minimum) or max(minimum) < 0.45:
            continue
        slot = int(np.argmax(minimum))
        available.remove(sky.satellites.index(sats[slot]))
        doppler = -RF / grid.LIGHT_SPEED_KM_S * np.sum(rays[slot] * v[slot], axis=1)
        f = doppler + random.uniform(-400_000, 200_000) + random.normal(0, 5, size=len(time))
        arcs.append(dict(arc=len(arcs), time=time.tolist(), frequency=f.tolist()))
    if len(arcs) < 8:
        raise ValueError("simulation needs at least eight visible distinct orbits")
    return dict(clock=clock, arcs=arcs)


def cases(raw):
    physical = list(recordings(raw))
    if len({v[0]["site"] for v in physical}) != 8:
        raise ValueError("expected eight first recordings from eight physical StarLoc sites")
    b, o, cat = physical[0]
    sim = simulation(o["clock"], cat)
    observed = dict(
        site="portugal-simulation",
        original_case=None,
        recording="portugal-simulation",
        native_file=None,
        native_sha256=None,
        catalogue_sha256=b["catalogue_sha256"],
        observation_source_sha256=None,
        origin=list(SIM_ORIGIN),
        cohort="simulation",
        sample_count=sum(len(a["time"]) for a in sim["arcs"]),
        arcs=len(sim["arcs"]),
    )
    for binding, observation, catalogue in [*physical, (observed, sim, cat)]:
        simulated = binding["cohort"] == "simulation"
        for number in (0,) if simulated else range(3):
            for panel in panels(
                binding["origin"], binding["catalogue_sha256"] + binding["recording"], number
            ):
                request = dict(observation=observation, catalogue=catalogue, offers=panel["offers"])
                base = binding | panel | dict(sample_sha256=digest(encoded(observation)))
                for method in METHODS:
                    yield base | dict(method=method, input_sha256=digest(encoded(request))), request
                if not simulated and number == 0 and not panel["slide"]:
                    shift = C_DELTA * (RF / 1e9 - 11.5)
                    shifted = [
                        dict(a, frequency=[y + shift for y in a["frequency"]])
                        for a in observation["arcs"]
                    ]
                    q = request | dict(
                        offers=request["offers"][::-1], observation=dict(observation, arcs=shifted)
                    )
                    yield base | dict(method="c_invariance", input_sha256=digest(encoded(q))), q


def frozen_sources():
    expected = prior.read(STUDY / "locks/engine.json")["contents"]["files"]
    for name in ("__init__.py", "grid.py", "receiver.py"):
        part = "engine/" + name
        path = STUDY / part
        prior.authority._read(path, expected[part])
        yield path, "/worker/" + part


def run_one(cpu, binding, packet):
    method = binding["method"]
    argv = prior.command(cpu)
    extra = [
        (path, str(Path("/worker") / path.relative_to(ROOT)))
        for path in (Path(model.__file__), Path(shape.__file__))
    ]
    argv[-4:-4] = [
        part
        for source, mount in [*extra, *frozen_sources()]
        for part in ("--ro-bind", str(source), mount)
    ]
    argv[-1] = WORKER
    argv.append(method)
    start = perf_counter()
    try:
        run = subprocess.run(
            argv, input=encoded(packet), capture_output=True, check=True, timeout=CAP
        )
        outcome = json.loads(run.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        stderr = (getattr(exc, "stderr", None) or b"").decode(errors="replace").strip()
        state = "timed_out" if isinstance(exc, subprocess.TimeoutExpired) else "failed"
        outcome = dict(status=state, reason=stderr[-1500:] or str(exc))
    print(
        binding["recording"],
        binding["trial"],
        int(binding["slide"]),
        method,
        outcome["status"],
        round(perf_counter() - start, 2),
        flush=True,
    )
    return binding | outcome | dict(elapsed_s=perf_counter() - start, cpu=cpu)


def run(raw):
    paths = [
        *prior.sources(),
        Path(shape.__file__),
        Path(model.__file__),
        Path(__file__),
        OUT / "PROTOCOL.md",
        prior.OUT / "prediction-lock.json",
        OUT.parents[1] / "original-schedule/beacon-transfer/prediction-lock.json",
        STUDY / "field-receipt.json",
        STUDY / "locks/engine.json",
        *(path for path, _ in frozen_sources()),
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
        ROOT / "src/leo/sky/sampling.py",
    ]
    hashes = {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in paths}
    save_json(OUT / "source-lock.json", hashes)
    planned = list(cases(raw))
    save_json(
        OUT / "blind-plan.json",
        dict(
            cpus=CPUS,
            cap_s=CAP,
            rows=[binding for binding, _ in planned],
            truth_sha256=prior.read(STUDY / "field-receipt.json")["sealed_truth_sha256"],
        ),
    )

    def lane(i):
        return [run_one(CPUS[i], binding, p) for binding, p in planned[i :: len(CPUS)]]

    start = perf_counter()
    with ThreadPoolExecutor(len(CPUS)) as pool:
        batches = list(pool.map(lane, range(len(CPUS))))
    if any(digest((ROOT / path).read_bytes()) != expected for path, expected in hashes.items()):
        raise ValueError("a declared source changed during prediction")
    rows = [r for batch in batches for r in batch]
    files = {
        name: digest((OUT / name).read_bytes()) for name in ("source-lock.json", "blind-plan.json")
    }
    files[ARCHIVE] = pack(OUT, ARCHIVE, rows)
    save_json(
        OUT / "prediction-lock.json",
        dict(files=files, calls=len(rows), campaign_wall_s=perf_counter() - start),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    run(parser.parse_args().raw)
