"""Training-only adapters for the historical cold/shape six-proposal chain.

The first stage produces the required Model B shape parents, not six proposals
or accuracy. Historical wrappers that prepare held data or run zero-c are never
used. Subsequent stages must retain the original cold/shape source distinction.
"""

import json
import time
from pathlib import Path

import ds21_fitted_discovery as discovery
import ds21_shape as shape
import numpy as np
from ds20_channel_corpus import digest
from ds21_common import immutable, json_value

from leo.analysis.research.doppler_shape_orbits import DopplerShapeOrbitObjective, fit_doppler_shape

LABEL = "DS21-007"
VIEWS = ("all", "low", "high")
SHAPE_VIEWS = ("low", "high", "all")
POLICY = dict(
    schema="ds21-fitted-proposal-shape-stage-v1", label=LABEL, stage="shape", arm="fitted-c",
    views=list(VIEWS), starts=3, maximum_optimizer_calls=9,
    fit_seconds=20, iterations=600, sigma_hz=400.0, timing_sigma_s=2.0,
    sequence="Original training bootstrap tracklets; exact RX/channel/RF; gap<=4s; alias splits",
    selector="Each low/high/all fitted-c shape winner; replaces historical zero-c selector only",
    c_interpretation="RF-constant sequence offsets project c out; not learned RF calibration",
    preparation_seconds=60, internal_seconds=240,
    external_term_seconds=255, external_kill_seconds=260,
    failed_retry=False, held_preparation=False, held_projection=False, reference_usage="none",
    output_scope="Model B shape parents only; six-pool requires fresh/hybrid/cold parents",
)


def read(path):
    return json.loads(Path(path).read_bytes())


def binding(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=digest(path))


def read_bound(row):
    if binding(row["path"]) != row:
        raise ValueError("fitted proposal ancestor binding changed")
    return read(row["path"])


def validate_archives(directory, source):
    """Verify historical subset, allowing genuinely new adapter imports."""
    if set(source["source_sha256"]) != set(source["snapshot_paths"]):
        raise ValueError("fitted proposal source archive inventory changed")
    for filename, sha in source["source_sha256"].items():
        relative = Path(source["snapshot_paths"][filename])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid fitted proposal source archive path")
        if digest(Path(filename)) != sha or digest(Path(directory) / relative) != sha:
            raise ValueError("fitted proposal live/archive scientific source changed")


def read_discovery(directory):
    """Bind original census, partition, causal full bank and three saved states.

    The existing discovery validator replays cached point selection only; no
    preparation, orbit prediction, bootstrap or optimizer is invoked here.
    """
    directory = Path(directory).resolve()
    frozen, source = read(directory / "protocol.json"), read(directory / "source-protocol.json")
    if frozen["policy"] != discovery.POLICY or source["policy"] != discovery.POLICY:
        raise ValueError("original fitted-only discovery policy changed")
    if frozen["source_protocol"] != binding(directory / "source-protocol.json"):
        raise ValueError("original discovery source protocol changed")
    validate_archives(directory, source)
    for key in ("membership", "census", "input"):
        read_bound(source[key])
    member, membership, census = discovery.inventory(
        source["membership"]["path"], source["census"]["path"]
    )
    snapshot = frozen["snapshot"]
    if (
        member != source["member"] or member["label"] != LABEL
        or frozen["prior"] != membership["prior"]
        or snapshot["collected_utc_ns"] >= frozen["start_utc_ns"]
        or digest(Path(snapshot["path"])) != snapshot["sha256"]
    ):
        raise ValueError("original discovery member/prior/causal catalogue changed")
    sha = digest(directory / "protocol.json")
    bank, bank_receipt = discovery.load_bank(directory, sha)
    if read(directory / "bank-launch.json") != dict(protocol_sha256=sha) or read(
        directory / "bank-termination.json"
    ) != dict(protocol_sha256=sha, bank=binding(directory / "bank.json")):
        raise ValueError("original discovery bank completion changed")
    points = discovery.AuditedPoints(directory, sha, bank, frozen, time.monotonic())
    terminal = discovery.validate_terminal(directory, frozen, bank, points)
    completions = []
    for launch in (directory / "slices").glob("*-launch.json"):
        done = launch.with_name(launch.name.replace("-launch", "-termination"))
        if not done.exists():
            raise ValueError("original discovery has an orphan slice")
        status = read(done)
        claimed = read(launch)
        if (
            claimed["protocol_sha256"] != sha or status["protocol_sha256"] != sha
            or claimed["slice_id"] != status["slice_id"]
            or launch.name != f"{claimed['slice_id']:03d}-launch.json"
            or status["state"] not in ("checkpointed", "complete")
        ):
            raise ValueError("original discovery slice authority changed")
        completions.append(status["state"])
    # Published discovery terminals have no state field; completion is in the
    # immutable slice termination, plus exact complete point/terminal coverage.
    if "complete" not in completions or not terminal["result"]["available"]:
        raise ValueError("completed three-state fitted discovery required")
    rows = terminal["result"]["selected"]
    indices = sorted({i for row in rows for i in row["satellite_indices"]},
                     key=lambda i: bank.numbers[i])
    return dict(
        directory=directory, frozen=frozen, source_protocol=source,
        member=member, membership=membership, census=census,
        full_bank=bank, bank=bank.select(indices), candidate_full_indices=indices,
        discovery=terminal["result"], protocol_sha256=sha,
        authority=dict(protocol=binding(directory / "protocol.json"),
                       source_protocol=binding(directory / "source-protocol.json"),
                       terminal=binding(directory / "terminal.json"),
                       bank_receipt=binding(directory / "bank.json"), bank=bank_receipt["bank"],
                       membership=source["membership"], census=source["census"],
                       input=source["input"], snapshot_sha256=snapshot["sha256"]),
    )


def fitted_shape_proposals(terminal):
    """Required low/high/all shape parents; no alternative/discovery substitution."""
    proposals = []
    if terminal.get("state") != "complete" or terminal.get("reference_usage") != "none":
        raise ValueError("sealed fitted-only shape parent required")
    for view in SHAPE_VIEWS:
        rows = [r for r in terminal["rows"]
                if r["view"] == view and r.get("rf_arm") == "fitted-c"]
        if len(rows) != 1 or not rows[0].get("winner"):
            raise ValueError(f"fitted shape proposal unavailable: {view}")
        winner = rows[0]["winner"]
        if not winner["stationary"] or not np.isfinite(winner["theta"]).all():
            raise ValueError(f"fitted shape proposal not stationary: {view}")
        proposals.append(dict(source_view=view, point_km=winner["theta"][:2]))
    return proposals


def freeze(stage, directory, *, discovery_directory, parent_directory=None):
    """Freeze shape parent work before any new training preparation or inference."""
    if stage != "shape" or parent_directory is not None:
        raise ValueError("this adapter slice implements the prerequisite shape stage only")
    directory = Path(directory).resolve()
    parent = read_discovery(discovery_directory)
    sources = discovery.scientific_sources()
    for filename in (Path(__file__), Path(shape.__file__)):
        sources[str(filename.resolve())] = digest(filename)
    protocol = dict(
        policy=POLICY, discovery_directory=str(parent["directory"]),
        discovery_authority=parent["authority"],
        prepared=parent["frozen"]["prepared"], partition=parent["frozen"]["partition"],
        prior=parent["frozen"]["prior"], training_frames=parent["frozen"]["training_frames"],
        bank_nodes_interval_s=[float(parent["bank"].nodes_s[0]),
                               float(parent["bank"].nodes_s[-1])],
        full_bank_count=len(parent["full_bank"].numbers),
        candidate_full_indices=parent["candidate_full_indices"],
        candidate_numbers=parent["bank"].numbers.tolist(),
        starts=[[row["east_km"], row["north_km"]] for row in parent["discovery"]["selected"]],
        source_sha256=sources, snapshot_paths=discovery.archive_sources(directory, sources),
        reference_usage="none", held_preparation=False,
    )
    immutable(directory / "protocol.json", protocol)
    return protocol


def _validate_row(row, view, frozen):
    if (
        row["view"] != view or row["rf_arm"] != "fitted-c"
        or row["prepared_sha256"] != frozen["prepared"][view]
        or len(row["attempts"]) != 3
    ):
        raise ValueError("shape row view/arm/preparation/start inventory changed")
    for fit in row["attempts"]:
        theta = np.asarray(fit["theta"])
        if theta.shape != (4,) or not np.isfinite(theta).all():
            raise ValueError("shape fitted-c physical layout changed")
        frame = frozen["training_frames"][view]
        lower = max(-10, frozen["bank_nodes_interval_s"][0] - frame["minimum_time_s"])
        upper = min(10, frozen["bank_nodes_interval_s"][1] - frame["maximum_time_s"])
        if fit["stationary"] and (
            not np.isfinite(fit["objective"]) or not np.isfinite(fit["stationarity"])
            or fit["stationarity"] > .001
            or np.hypot(*theta[:2]) > frozen["prior"]["radius_km"] + 1e-5
            or not lower - 1e-6 <= theta[2] <= upper + 1e-6
            or abs(theta[3]) > 5000 + 1e-6
        ):
            raise ValueError("shape stationary physical bounds changed")
    stationary = [fit for fit in row["attempts"] if fit["stationary"]]
    winner = min(stationary, key=lambda x: x["objective"]) if stationary else None
    if row["winner"] != winner:
        raise ValueError("shape row training minimum selector changed")


def run(directory, *, slice_id, maximum_seconds=None):
    """One explicit bounded shape slice, retaining completed views and failures."""
    directory = Path(directory).resolve()
    maximum_seconds = POLICY["internal_seconds"] if maximum_seconds is None else maximum_seconds
    if type(slice_id) is not int or slice_id < 0 or not 0 < maximum_seconds <= 240:
        raise ValueError("explicit nonnegative stage slice and at most240 seconds required")
    begun = time.monotonic()
    frozen = read(directory / "protocol.json")
    if frozen["policy"] != POLICY:
        raise ValueError("fitted shape stage policy changed")
    validate_archives(directory, frozen)
    parent = read_discovery(frozen["discovery_directory"])
    if parent["authority"] != frozen["discovery_authority"]:
        raise ValueError("fitted shape discovery authority changed")
    if (
        parent["candidate_full_indices"] != frozen["candidate_full_indices"]
        or parent["bank"].numbers.tolist() != frozen["candidate_numbers"]
        or len(parent["full_bank"].numbers) != frozen["full_bank_count"]
        or any(parent["frozen"][key] != frozen[key]
               for key in ("prepared", "partition", "prior", "training_frames"))
        or [[row["east_km"], row["north_km"]] for row in parent["discovery"]["selected"]]
        != frozen["starts"]
    ):
        raise ValueError("shape frozen training inputs differ from original discovery")
    sha = digest(directory / "protocol.json")
    rows = []
    names = {f"{view}-fitted-c" for view in VIEWS}
    for folder in ("rows", "launches", "terminations"):
        paths = list((directory / folder).glob("*.json"))
        if not {p.stem for p in paths} <= names:
            raise ValueError("extra shape view or forbidden RF arm")
    for view in VIEWS:
        name = f"{view}-fitted-c.json"
        path = directory / "rows" / name
        identity = dict(protocol_sha256=sha, view=view, arm="fitted-c")
        launch, done = directory / "launches" / name, directory / "terminations" / name
        if path.exists():
            row = read(path)
            _validate_row(row, view, frozen)
            if (
                not launch.exists() or not done.exists() or read(launch) != identity
                or read(done) != dict(**identity, row=binding(path))
            ):
                raise ValueError("shape row completion authority changed")
            rows.append(row)
        elif launch.exists() or done.exists():
            raise ValueError("orphan shape view; no retry")
    terminal_path = directory / "terminal.json"
    slices = directory / "slices"
    complete_slice = False
    for launch in slices.glob("*-launch.json"):
        done = launch.with_name(launch.name.replace("-launch", "-termination"))
        if not done.exists() or read(done)["state"] not in ("checkpointed", "complete"):
            raise ValueError("orphan/failed shape stage slice; no automatic retry")
        claimed, finished = read(launch), read(done)
        if (
            claimed["protocol_sha256"] != sha or finished["protocol_sha256"] != sha
            or claimed["slice_id"] != finished["slice_id"]
            or launch.name != f"{claimed['slice_id']:03d}-launch.json"
        ):
            raise ValueError("shape stage slice identity changed")
        complete_slice |= finished["state"] == "complete"
    if terminal_path.exists():
        terminal = read(terminal_path)
        if (
            terminal["protocol_sha256"] != sha or terminal["rows"] != rows or len(rows) != 3
            or terminal["optimizer_calls"] != 9 or terminal["arm"] != "fitted-c"
            or terminal["reference_usage"] != "none" or terminal["held_usage"] != "none"
            or not complete_slice
        ):
            raise ValueError("shape terminal coverage/completion changed")
        return terminal
    claim = slices / f"{slice_id:03d}-launch.json"
    claim.parent.mkdir(parents=True, exist_ok=True)
    with claim.open("x") as stream:
        json.dump(dict(protocol_sha256=sha, slice_id=slice_id), stream)
    status = dict(protocol_sha256=sha, slice_id=slice_id, state="failed")
    try:
        with discovery.slice_bound(max(.001, min(
            POLICY["preparation_seconds"], maximum_seconds - (time.monotonic() - begun)
        ))):
            case = discovery.prepare_training_case(
                parent["member"], parent["membership"], parent["census"]
            )
            discovery.validate_preparation(case, parent["frozen"])
        with discovery.slice_bound(max(.001, maximum_seconds - (time.monotonic() - begun))):
            starts = frozen["starts"]
            for view in VIEWS:
                path = directory / "rows" / f"{view}-fitted-c.json"
                if path.exists():
                    continue
                if time.monotonic() - begun + 3 * 20 + 10 >= maximum_seconds:
                    status.update(state="checkpointed", next_view=view)
                    return dict(**status, completed_views=len(rows))
                prepared = case["prepared"][view]
                sequences = shape.supported_sequences(
                    prepared.observations, prepared.bootstrap_tracks
                )
                if not sequences:
                    raise ValueError(f"required original shape support unavailable: {view}")
                model = DopplerShapeOrbitObjective(
                    prepared.observations, parent["bank"], case["prior"], sequences
                )
                identity = dict(protocol_sha256=sha, view=view, arm="fitted-c")
                launch = directory / "launches" / path.name
                launch.parent.mkdir(parents=True, exist_ok=True)
                with launch.open("x") as stream:
                    json.dump(identity, stream)
                result = fit_doppler_shape(model, starts, rf_arm="fitted-c", maximum_seconds=20,
                                           maximum_iterations=600)
                result.update(
                    view=view, label=LABEL,
                    support=shape.sequence_audit(prepared.observations, sequences),
                    prepared_sha256=prepared.evidence_sha256,
                )
                result = json_value(result)
                _validate_row(result, view, frozen)
                immutable(path, result)
                immutable(
                    directory / "terminations" / path.name, dict(**identity, row=binding(path))
                )
                rows.append(read(path))
            # Missing stationary required views are retained, never substituted.
            validate_archives(directory, frozen)
            if read_discovery(frozen["discovery_directory"])["authority"] != parent["authority"]:
                raise ValueError("shape discovery ancestor changed during numerical work")
            terminal = dict(state="complete", label=LABEL, model="B", arm="fitted-c",
                            protocol_sha256=sha, rows=rows, optimizer_calls=9,
                            reference_usage="none", held_usage="none",
                            elapsed_s=time.monotonic() - begun)
            immutable(terminal_path, terminal)
            status["state"] = "complete"
            return read(terminal_path)
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        status["elapsed_s"] = time.monotonic() - begun
        immutable(slices / f"{slice_id:03d}-termination.json", status)
