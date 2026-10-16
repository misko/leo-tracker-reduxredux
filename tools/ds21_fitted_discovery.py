"""Training-only fitted-c initialization of one frozen development recording.

Source/input freeze precedes preparation. A second protocol pins the exact
census preparation and causal TLE bytes before any orbit propagation or fit.
Discovery states are neither six proposals nor an accuracy result.
"""

import argparse
import json
import runpy
import signal
import time
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path

import ds21_common as common
import numpy as np
from ds20_channel_corpus import ADAPTER, digest
from ds20_channel_training import LocalPoints
from ds20_channel_validate import metadata_coverage
from ds21_joint_candidates import loaded_source_hashes

from leo.analysis.channel_group_calibration import group_frame
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import ALIAS_HZ, zero_sum_basis
from leo.analysis.regional_position_search import hierarchical_search
from leo.application.channel_group_discovery import DiscoverySliceExpired, discover_channel_groups
from leo.application.channel_group_holdout import partition_channel_probes
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior
from leo.operations.tle_archive import TleArchiveReader, TleSnapshotRef
from leo.sky.propagation import parse_element_sets

LABEL = "DS21-007"
POLICY = dict(
    schema="ds21-training-fitted-discovery-v1",
    label=LABEL,
    arm="fitted-c",
    views=["all", "low", "high"],
    partition_seed=20261012,
    block_seconds=20,
    points=100,
    levels_km=[100.0, 50.0, 25.0, 12.5],
    priority_view="all",
    clock_initializer="Original zero receiver knots on metadata-derived 30-second nodes",
    bootstrap_seconds=5,
    fixed_position_fit_seconds=5,
    fixed_position_fit_iterations=200,
    bank_seconds=180,
    preparation_seconds=60,
    internal_seconds=480,
    external_term_seconds=495,
    external_kill_seconds=500,
    point_admission_reserve_seconds=31,
    orphan_retry=False,
    failed_point_retry=False,
    held_preparation=False,
    held_projection=False,
    reference_usage="none",
    release_target="Every eligible acquired CH1-8 member below 0.5 km; fitted c only",
    output_scope="Development initialization only; not six proposals or accuracy/release",
)


class SliceHardStop(BaseException):
    """Escapes discovery's per-view TimeoutError handler at the whole-slice bound."""


@contextmanager
def slice_bound(seconds):
    previous = signal.getsignal(signal.SIGALRM)

    def expired(*_):
        raise SliceHardStop("Discovery whole-slice deadline exhausted")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def read(path):
    return json.loads(Path(path).read_bytes())


def binding(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=digest(path))


def scientific_sources():
    """Preload adapter and native binary without preparing data or predicting."""
    from leo.analysis import _regional_orbits, regional_position_bank

    runpy.run_path(str(ADAPTER))
    sources = loaded_source_hashes()
    for path in (
        Path(__file__),
        ADAPTER,
        Path(_regional_orbits.__file__),
        Path(regional_position_bank.__file__).with_name("_regional_orbits.cpp"),
    ):
        path = path.resolve()
        sources[str(path)] = digest(path)
    return sources


def archive_sources(directory, sources):
    paths = {}
    for index, (filename, sha) in enumerate(sorted(sources.items())):
        relative = f"source-snapshot/{index:04d}-{Path(filename).name}"
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if digest(target) != sha:
                raise ValueError("Discovery source archive changed")
        else:
            target.write_bytes(Path(filename).read_bytes())
        paths[filename] = relative
    return paths


def validate_sources(directory, frozen):
    if scientific_sources() != frozen["source_sha256"]:
        raise ValueError("Discovery scientific source closure changed")
    if set(frozen["snapshot_paths"]) != set(frozen["source_sha256"]):
        raise ValueError("Incomplete discovery source archive")
    for filename, relative in frozen["snapshot_paths"].items():
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid discovery source archive path")
        if digest(directory / relative) != frozen["source_sha256"][filename]:
            raise ValueError("Discovery source archive changed")


def inventory(membership_path, census_path):
    membership, census = read(membership_path), read(census_path)
    members = [m for m in membership["members"] if m["label"] == LABEL]
    if len(members) != 1:
        raise ValueError("Exactly the fixed first missing development label required")
    member = members[0]
    if (
        member["role"] != "development"
        or not member["eight_channel"]
        or member["channels"] != common.VIEWS["all"]
        or not member["session_id"].startswith("fast-")
        or member["input"] is None
    ):
        raise ValueError("Qualified fast CH1-8 development input required; evaluation refused")
    if (
        census["membership_sha256"] != digest(Path(membership_path))
        or census["label"] != LABEL
        or census["role"] != "development"
        or census["state"] != "prepared"
        or set(census["views"]) != set(common.VIEWS)
        or census["failures"]
    ):
        raise ValueError("Complete original three-view census required")
    if binding(member["input"]["path"]) != member["input"]:
        raise ValueError("Sealed development tracking input changed")
    return member, membership, census


def prepare_training_case(member, membership, census):
    source = common.load_source(member, membership)
    split = partition_channel_probes(
        source, seed=POLICY["partition_seed"], block_seconds=POLICY["block_seconds"]
    )
    prepared = {}
    for view, channels in common.VIEWS.items():
        training = replace(
            split.training, probes=tuple(p for p in split.training.probes if p.channel in channels)
        )
        value = prepare_position_windows(training)
        actual = dict(
            windows=len(value.observations.window_ids),
            tracks=len(value.bootstrap_tracks),
            evidence_sha256=value.evidence_sha256,
        )
        if actual != census["views"][view]:
            raise ValueError(f"Original training census evidence differs: {view}")
        prepared[view] = value
    if (
        source.session_id != census["native_session_id"]
        or source.sample_rate_hz != census["sample_rate_hz"]
        or split.seed != census["split_seed"]
        or list(split.held_blocks) != census["held_blocks"]
    ):
        raise ValueError("Original training partition/session metadata differs")
    envelope, nodes = metadata_coverage(source, split)
    return dict(
        source=source,
        split=split,
        prepared=prepared,
        envelope=envelope,
        nodes=nodes,
        prior=RegionalPrior(**membership["prior"]),
    )


def freeze(
    directory,
    *,
    label=LABEL,
    membership_path=common.OUTPUT / "membership.json",
    census_path=None,
    tle_root=Path("/var/lib/leo/tle"),
):
    if label != LABEL:
        raise ValueError("Only frozen DS21-007 initialization authorized")
    directory, membership_path = Path(directory).resolve(), Path(membership_path).resolve()
    census_path = (
        Path(census_path).resolve()
        if census_path
        else membership_path.parent / "local/census" / f"{LABEL}.json"
    )
    member, membership, census = inventory(membership_path, census_path)
    sources = scientific_sources()
    source_protocol = dict(
        policy=POLICY,
        phase="Source/input pin before training preparation; zero propagation/fits",
        membership=binding(membership_path),
        census=binding(census_path),
        input=member["input"],
        member=member,
        source_sha256=sources,
        snapshot_paths=archive_sources(directory, sources),
    )
    common.immutable(directory / "source-protocol.json", source_protocol)
    validate_sources(directory, source_protocol)
    with slice_bound(POLICY["preparation_seconds"]):
        case = prepare_training_case(member, membership, census)
    archive = TleArchiveReader(Path(tle_root))
    snapshot = archive.select_latest_before(case["prepared"]["all"].start_utc_ns)
    archive.read(snapshot)  # Verify immutable bytes before any numerical bank work.
    protocol = dict(
        policy=POLICY,
        source_protocol=binding(directory / "source-protocol.json"),
        phase="Exact census training preparation and causal catalogue pin; zero propagation/fits",
        start_utc_ns=case["prepared"]["all"].start_utc_ns,
        prepared={v: p.evidence_sha256 for v, p in case["prepared"].items()},
        training_frames={
            view: dict(
                time_center_s=p.observations.time_center_s,
                rf_center_hz=p.observations.rf_center_hz,
                minimum_time_s=float(p.observations.times_s.min()),
                maximum_time_s=float(p.observations.times_s.max()),
                **asdict(group_frame(p.observations.receiver, p.observations.channel >= 5)),
            )
            for view, p in case["prepared"].items()
        },
        clock_nodes_s=case["nodes"].tolist(),
        prior=asdict(case["prior"]),
        snapshot=dict(
            path=str(snapshot.path.resolve()),
            sha256=snapshot.digest,
            provider=snapshot.provider,
            collected_utc_ns=snapshot.collected_utc_ns,
            byte_size=snapshot.byte_size,
            archive_root=str(Path(tle_root).resolve()),
        ),
        partition=dict(
            seed=case["split"].seed,
            block_seconds=case["split"].block_seconds,
            held_blocks=list(case["split"].held_blocks),
            assignments=[list(a) for a in case["split"].assignments],
        ),
    )
    validate_sources(directory, source_protocol)
    common.immutable(directory / "protocol.json", protocol)
    return protocol


def validate_freeze(directory):
    frozen = read(directory / "protocol.json")
    source = read(directory / "source-protocol.json")
    if frozen["policy"] != POLICY or source["policy"] != POLICY:
        raise ValueError("Discovery policy changed")
    if frozen["source_protocol"] != binding(directory / "source-protocol.json"):
        raise ValueError("Discovery source protocol changed")
    validate_sources(directory, source)
    for key in ("membership", "census", "input"):
        if binding(source[key]["path"]) != source[key]:
            raise ValueError(f"Discovery {key} binding changed")
    member, membership, census = inventory(source["membership"]["path"], source["census"]["path"])
    if member != source["member"] or frozen["prior"] != membership["prior"]:
        raise ValueError("Discovery member/prior changed")
    s = frozen["snapshot"]
    snapshot = TleSnapshotRef(
        s["collected_utc_ns"],
        s["provider"],
        s["sha256"].removeprefix("sha256:"),
        s["byte_size"],
        Path(s["path"]),
    )
    if (
        not snapshot.collected_utc_ns < frozen["start_utc_ns"]
        or binding(snapshot.path)["sha256"] != snapshot.digest
    ):
        raise ValueError("Discovery catalogue changed or is noncausal")
    return frozen, source, member, membership, census, snapshot


def validate_preparation(case, frozen):
    split = case["split"]
    actual = dict(
        seed=split.seed,
        block_seconds=split.block_seconds,
        held_blocks=list(split.held_blocks),
        assignments=[list(a) for a in split.assignments],
    )
    if (
        actual != frozen["partition"]
        or case["prepared"]["all"].start_utc_ns != frozen["start_utc_ns"]
        or {v: p.evidence_sha256 for v, p in case["prepared"].items()} != frozen["prepared"]
        or case["nodes"].tolist() != frozen["clock_nodes_s"]
    ):
        raise ValueError("Frozen training preparation/partition changed")


def load_bank(directory, protocol_sha):
    receipt = read(directory / "bank.json")
    if receipt["protocol_sha256"] != protocol_sha or receipt["bank"] != binding(
        directory / "bank.npz"
    ):
        raise ValueError("Discovery bank binding changed")
    with np.load(directory / "bank.npz", allow_pickle=False) as arrays:
        bank = PositionOrbitBank(
            *(arrays[k] for k in ("numbers", "nodes_s", "position_km", "velocity_km_s"))
        )
    if bank.numbers.tolist() != receipt["build"]["retained_numbers"]:
        raise ValueError("Discovery bank ordered catalogue changed")
    return bank, receipt


class AuditedPoints(LocalPoints):
    """Same get/put numerical port, with admission and immutable launch evidence."""

    def __init__(self, directory, protocol_sha, bank, frozen, deadline):
        super().__init__(directory / "points", protocol_sha)
        self.directory, self.bank, self.frozen, self.deadline = directory, bank, frozen, deadline

    def validate(self, key, row):
        point = f"point:{row['east_km']:g}:{row['north_km']:g}"
        indices = row["satellite_indices"]
        if (
            key != point
            or not np.isfinite([row["east_km"], row["north_km"]]).all()
            or np.hypot(row["east_km"], row["north_km"]) > self.frozen["prior"]["radius_km"]
            or len(indices) != len(set(indices))
            or any(type(i) is not int or not 0 <= i < len(self.bank.numbers) for i in indices)
            or row["catalogue_numbers"] != self.bank.numbers[indices].tolist()
            or row["catalogue_numbers"] != sorted(row["catalogue_numbers"])
            or not set(row["fits"]) <= set(common.VIEWS)
            or not set(row["failures"]) <= set(common.VIEWS)
        ):
            raise ValueError("Discovery point geometry/catalogue/view changed")
        clocks = 2 * (len(self.frozen["clock_nodes_s"]) - 2)
        for view, fit in row["fits"].items():
            v, n = np.asarray(fit["vector"]), np.asarray(fit["nuisance"])
            groups = len(fit["group_receivers"])
            frame = self.frozen["training_frames"][view]
            if v.shape != (7 + len(indices),):
                raise ValueError("Discovery point timing/vector layout changed")
            shifts = v[7] + zero_sum_basis(len(indices)) @ v[8:]
            minimum = max(-20.0, self.bank.nodes_s[0] - frame["minimum_time_s"])
            maximum = min(20.0, self.bank.nodes_s[-1] - frame["maximum_time_s"])
            if (
                v.shape != (7 + len(indices),)
                or n.shape != (clocks + groups,)
                or not np.isfinite(v).all()
                or not np.isfinite(n).all()
                or not np.allclose(v[:2], [row["east_km"], row["north_km"]], atol=1e-9, rtol=0)
                or abs(v[6]) > 5000 + 1e-7
                or abs(v[3]) > 60 + 1e-7
                or abs(v[5]) > 60 + 1e-7
                or abs(v[7]) > 10 + 1e-7
                or np.any(shifts < minimum - 1e-7)
                or np.any(shifts > maximum + 1e-7)
                or np.any(abs(n[:clocks]) > 2000 + 1e-7)
                or np.any(abs(n[clocks:]) > ALIAS_HZ / 2 + 1e-7)
                or not np.isfinite(
                    [fit["objective"], fit["likelihood_nll"], fit["stationarity"]]
                ).all()
                or fit["converged"] != (fit["stationarity"] <= 0.001)
                or fit["clock_coefficients"] != n[:clocks].tolist()
                or fit["group_offsets_hz"] != n[clocks:].tolist()
                or fit["group_drifts_hz_s"]
                or fit["group_clock_coefficients"]
                or fit["group_receivers"] != frame["receivers"]
                or fit["training_high_fractions"] != frame["high_fractions"]
                or fit["training_time_center_s"] != frame["time_center_s"]
                or fit["training_rf_center_hz"] != frame["rf_center_hz"]
            ):
                raise ValueError(f"Discovery point fit layout/limits/stationarity changed: {view}")
        all_fit = row["fits"].get("all", {})
        expected = all_fit["objective"] if all_fit.get("converged") else 1e100
        if row["selection_score"] != expected:
            raise ValueError("Discovery point training selector changed")

    def get(self, key):
        path = self.path(key)
        launch = self.directory / "point-launches" / path.name
        termination = self.directory / "point-terminations" / path.name
        identity = dict(protocol_sha256=self.binding, key=key)
        if path.exists():
            row = super().get(key)
            self.validate(key, row)
            if not launch.exists() or not termination.exists():
                raise ValueError("Orphan discovery point; no retry")
            if read(launch) != identity or read(termination) != dict(
                **identity, point=binding(path)
            ):
                raise ValueError("Discovery point completion binding changed")
            return row
        if launch.exists() or termination.exists():
            raise ValueError("Orphan discovery point; no retry")
        if time.monotonic() + POLICY["point_admission_reserve_seconds"] >= self.deadline:
            raise DiscoverySliceExpired(key)
        launch.parent.mkdir(parents=True, exist_ok=True)
        with launch.open("x") as stream:
            json.dump(identity, stream, allow_nan=False)
        return None

    def put(self, key, result):
        result = json.loads(json.dumps(common.json_value(result), allow_nan=False))
        self.validate(key, result)
        if read(self.directory / "point-launches" / self.path(key).name) != dict(
            protocol_sha256=self.binding, key=key
        ):
            raise ValueError("Discovery point missing atomic launch")
        super().put(key, result)
        common.immutable(
            self.directory / "point-terminations" / self.path(key).name,
            dict(protocol_sha256=self.binding, key=key, point=binding(self.path(key))),
        )

    def completed(self):
        rows = {}
        for path in self.root.glob("*.json"):
            key = read(path)["key"]
            if self.path(key) != path:
                raise ValueError("Discovery point key/path changed")
            rows[key] = self.get(key)
        if len(rows) > POLICY["points"]:
            raise ValueError("Discovery point budget exceeded")
        expected = {self.path(k).name for k in rows}
        for folder in ("point-launches", "point-terminations"):
            if {p.name for p in (self.directory / folder).glob("*.json")} != expected:
                raise ValueError("Orphan discovery point; no retry")
        return rows


def validate_terminal(directory, frozen, bank, point_port):
    terminal = read(directory / "terminal.json")
    rows = point_port.completed()
    result = terminal["result"]
    if (
        terminal["protocol"] != binding(directory / "protocol.json")
        or terminal["bank"] != binding(directory / "bank.json")
        or terminal["points"] != {k: binding(point_port.path(k)) for k in rows}
        or result["points"] != len(rows)
        or result["priority_view"] != "all"
        or result["available"] != (len(result["selected"]) == 3)
    ):
        raise ValueError("Discovery terminal bindings/coverage changed")

    def score(east, north):
        key = f"point:{east:g}:{north:g}"
        if key not in rows:
            raise ValueError("Discovery terminal hierarchy lacks completed point")
        return rows[key]["selection_score"]

    replay = hierarchical_search(
        score,
        radius_km=frozen["prior"]["radius_km"],
        levels_km=POLICY["levels_km"],
        budget_points=POLICY["points"],
        edge_priority="nearest",
    )
    if json.loads(json.dumps(common.json_value(asdict(replay)))) != result["search"]:
        raise ValueError("Discovery terminal hierarchy changed")
    ranked = []
    for view in ("low", "high", "all"):
        eligible = [r for r in rows.values() if r["fits"].get(view, {}).get("converged")]
        if eligible:
            ranked.append(
                min(
                    eligible,
                    key=lambda r: (r["fits"][view]["objective"], r["east_km"], r["north_km"]),
                )
            )
    ranked.extend(
        sorted(
            (r for r in rows.values() if r["selection_score"] < 1e100),
            key=lambda r: (r["selection_score"], r["east_km"], r["north_km"]),
        )
    )
    selected = []
    for row in ranked:
        if all(
            np.hypot(row["east_km"] - r["east_km"], row["north_km"] - r["north_km"]) >= 12.5
            for r in selected
        ):
            selected.append(row)
        if len(selected) == 3:
            break
    if selected != result["selected"]:
        raise ValueError("Discovery terminal training selection changed")
    return terminal


def run(directory, *, slice_id, maximum_seconds=480):
    begun = time.monotonic()
    directory = Path(directory).resolve()
    if (
        type(slice_id) is not int
        or slice_id < 0
        or not np.isfinite(maximum_seconds)
        or not 0 < maximum_seconds <= POLICY["internal_seconds"]
    ):
        raise ValueError("Explicit nonnegative slice and at most 480 seconds required")
    frozen, source, member, membership, census, snapshot = validate_freeze(directory)
    protocol_sha = digest(directory / "protocol.json")
    slices = directory / "slices"
    for path in slices.glob("*-launch.json"):
        done = path.with_name(path.name.replace("-launch", "-termination"))
        if not done.exists() or read(done)["state"] not in ("checkpointed", "complete"):
            raise ValueError("Orphan/failed discovery slice; no automatic retry")
        for row in (read(path), read(done)):
            if (
                row["protocol_sha256"] != protocol_sha
                or path.name != f"{row['slice_id']:03d}-launch.json"
            ):
                raise ValueError("Discovery slice identity changed")
    if (directory / "terminal.json").exists():
        bank, _ = load_bank(directory, protocol_sha)
        if read(directory / "bank-launch.json") != dict(protocol_sha256=protocol_sha) or read(
            directory / "bank-termination.json"
        ) != dict(protocol_sha256=protocol_sha, bank=binding(directory / "bank.json")):
            raise ValueError("Discovery bank completion changed")
        return validate_terminal(
            directory, frozen, bank, AuditedPoints(directory, protocol_sha, bank, frozen, begun)
        )
    slices.mkdir(parents=True, exist_ok=True)
    claim = slices / f"{slice_id:03d}-launch.json"
    with claim.open("x") as stream:
        json.dump(dict(protocol_sha256=protocol_sha, slice_id=slice_id), stream)
    status = dict(protocol_sha256=protocol_sha, slice_id=slice_id, state="failed")
    try:
        with slice_bound(max(0.001, maximum_seconds - (time.monotonic() - begun))):
            case = prepare_training_case(member, membership, census)
            validate_preparation(case, frozen)
            if (directory / "bank.json").exists():
                bank, _ = load_bank(directory, protocol_sha)
                if read(directory / "bank-launch.json") != dict(
                    protocol_sha256=protocol_sha
                ) or read(directory / "bank-termination.json") != dict(
                    protocol_sha256=protocol_sha, bank=binding(directory / "bank.json")
                ):
                    raise ValueError("Discovery bank completion changed")
            else:
                launch = directory / "bank-launch.json"
                if launch.exists() or (directory / "bank.npz").exists():
                    raise ValueError("Orphan discovery bank; no retry")
                remaining = maximum_seconds - (time.monotonic() - begun)
                if remaining <= 1:
                    raise DiscoverySliceExpired("before-bank")
                with launch.open("x") as stream:
                    json.dump(dict(protocol_sha256=protocol_sha), stream)
                catalogue = parse_element_sets(
                    TleArchiveReader(Path(frozen["snapshot"]["archive_root"])).read(snapshot)
                )
                indices = [
                    i
                    for i, name in enumerate(catalogue.names)
                    if name.upper().startswith("STARLINK") and "DEB" not in name.upper()
                ]
                remaining = maximum_seconds - (time.monotonic() - begun)
                if remaining <= 0:
                    raise SliceHardStop("Discovery bank deadline exhausted")
                bank, receipt = build_regional_bank(
                    catalogue,
                    indices,
                    frozen["start_utc_ns"],
                    case["envelope"],
                    case["prior"],
                    maximum_seconds=min(POLICY["bank_seconds"], remaining),
                )
                temporary = directory / "bank.partial.npz"
                np.savez(
                    temporary,
                    **{
                        k: getattr(bank, k)
                        for k in ("numbers", "nodes_s", "position_km", "velocity_km_s")
                    },
                )
                temporary.replace(directory / "bank.npz")
                common.immutable(
                    directory / "bank.json",
                    dict(
                        protocol_sha256=protocol_sha,
                        bank=binding(directory / "bank.npz"),
                        build=asdict(receipt),
                    ),
                )
                common.immutable(
                    directory / "bank-termination.json",
                    dict(protocol_sha256=protocol_sha, bank=binding(directory / "bank.json")),
                )
            point_port = AuditedPoints(
                directory, protocol_sha, bank, frozen, begun + maximum_seconds
            )
            point_port.completed()
            remaining = maximum_seconds - (time.monotonic() - begun)
            if remaining <= POLICY["point_admission_reserve_seconds"]:
                raise DiscoverySliceExpired("before-next-point")
            result = discover_channel_groups(
                case["prepared"],
                bank,
                case["prior"],
                point_port,
                maximum_seconds=remaining,
                points=POLICY["points"],
                clock_nodes=case["nodes"],
                levels_km=POLICY["levels_km"],
                priority_view="all",
            )
            validate_sources(directory, source)
            rows = point_port.completed()
            common.immutable(
                directory / "terminal.json",
                dict(
                    protocol=binding(directory / "protocol.json"),
                    bank=binding(directory / "bank.json"),
                    points={k: binding(point_port.path(k)) for k in rows},
                    result=result,
                ),
            )
            validate_terminal(directory, frozen, bank, point_port)
            status["state"] = "complete"
    except DiscoverySliceExpired as error:
        status.update(state="checkpointed", reason=str(error))
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        status["elapsed_s"] = time.monotonic() - begun
        common.immutable(slices / f"{slice_id:03d}-termination.json", status)
    return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--slice-id", type=int)
    args = parser.parse_args()
    if args.action == "run" and args.slice_id is None:
        parser.error("run requires an explicitly authorized --slice-id")
    output = (
        freeze(args.directory)
        if args.action == "freeze"
        else run(args.directory, slice_id=args.slice_id)
    )
    print(json.dumps(common.json_value(output), allow_nan=False), flush=True)
