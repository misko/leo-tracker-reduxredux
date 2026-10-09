"""Unfrozen durable orchestration; no command-line recording execution entrypoint."""

import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import numpy as np
from adapter import PointEvaluator, predict_orbits
from traced_search import hierarchical_search

from leo.analysis.regional_position_bootstrap import BootstrapMatch, PositionBootstrap
from leo.analysis.regional_position_search import distinct_basins
from leo.application.hard60_runner import Hard60Configuration
from leo.application.regional_position_runner import json_value
from leo.contracts.digests import canonical_digest


class SliceExpired(Exception):
    pass


class ClaimedWithoutReceipt(Exception):
    pass


class CachedFailure(Exception):
    pass


def read(path):
    return json.loads(Path(path).read_text())


def append(path, value):
    """Publish a complete immutable JSON file using exclusive hard-link creation."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / ("." + path.name + "." + uuid.uuid4().hex)
    try:
        with temp.open("x") as handle:
            json.dump(json_value(value), handle, sort_keys=True, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def verify_plan(plan, repository):
    if plan["slice_count"] != 12 or plan["slice_seconds"] != 500:
        raise ValueError("fixed aggregate budget differs")
    if not plan["source_sha256"] or not plan["input_sha256"]:
        raise ValueError("source and input closures required")
    for entries in (plan["source_sha256"], plan["input_sha256"]):
        for name, digest in entries.items():
            if hashlib.sha256((Path(repository) / name).read_bytes()).hexdigest() != digest:
                raise ValueError("frozen file mismatch: " + name)
    required = (
        "input_manifest_sha256",
        "analysis_manifest_sha256",
        "evidence_sha256",
        "bank_sha256",
        "prior_sha256",
        "observations_sha256",
    )
    if any(not plan["identity"].get(field) for field in required):
        raise ValueError("incomplete physical input identity")
    if not plan.get("native_baseline"):
        raise ValueError("frozen native trace required")
    return canonical_digest(plan)


class DurableCache:
    def __init__(self, directory, digest, deadline, *, clock=time.monotonic):
        self.directory, self.digest, self.deadline, self.clock = (
            Path(directory),
            digest,
            deadline,
            clock,
        )

    def fetch(self, key, operation, *, reserve_seconds=15):
        if self.clock() >= self.deadline:
            raise SliceExpired(key)
        token = canonical_digest(key).split(":")[-1]
        path = self.directory / (token + ".json")
        claim = self.directory / (token + ".claim.json")
        identity = {"protocol_sha256": self.digest, "key": key}
        if path.exists():
            row = read(path)
            if any(row.get(k) != v for k, v in identity.items()):
                raise ValueError("cache binding mismatch")
            if row.get("status") not in ("complete", "failed"):
                raise ValueError("invalid cached status")
            if row["status"] == "failed":
                raise CachedFailure(row["error"])
            return row["value"]
        if claim.exists():
            row = read(claim)
            if row != identity:
                raise ValueError("claim binding mismatch")
            raise ClaimedWithoutReceipt(str(claim))
        if self.clock() + reserve_seconds >= self.deadline:
            raise SliceExpired(key)
        append(claim, identity)
        begun = self.clock()
        try:
            value = operation()
        except Exception as error:
            # Process interruption (BaseException) deliberately leaves a claim.
            append(
                path,
                dict(
                    identity,
                    status="failed",
                    error=f"{type(error).__name__}: {error}",
                    elapsed_s=self.clock() - begun,
                ),
            )
            raise CachedFailure(str(error)) from error
        append(path, dict(identity, status="complete", value=value, elapsed_s=self.clock() - begun))
        return read(path)["value"]


def case_identity(case):
    observations, bank = case["observations"], case["bank"]
    return dict(
        case["identity"],
        bank_sha256=canonical_digest(json_value(bank)),
        prior_sha256=canonical_digest(json_value(case["prior"])),
        observations_sha256=canonical_digest(json_value(observations)),
    )


def native_parity(search, baseline):
    rows = search.evaluations
    if len(rows) != len(baseline):
        raise ValueError("native baseline coverage mismatch")
    for actual, expected in zip(rows, baseline, strict=True):
        if not all(
            np.isfinite(expected[k]) for k in ("east_km", "north_km", "spacing_km", "score")
        ) or not np.isfinite(actual.score):
            raise ValueError("nonfinite native baseline value")
        if (actual.east_km, actual.north_km, actual.spacing_km) != tuple(
            expected[k] for k in ("east_km", "north_km", "spacing_km")
        ) or abs(actual.score - expected["score"]) > 1e-6:
            raise ValueError("native baseline trace/score mismatch")


def run_slice(
    plan, repository, output, loader, *, clock=time.monotonic, evaluator_factory=PointEvaluator
):
    """One member, all four searches, twelve total slices (not twelve per arm).

    Loader is a narrow port returning inference-only observations/bank/prior/tracks
    plus exact input manifests/evidence. It is called after the immutable claim.
    """
    digest = verify_plan(plan, repository)
    directory = Path(output)
    terminal = directory / "result.json"
    if terminal.exists():
        row = read(terminal)
        if row["protocol_sha256"] != digest:
            raise ValueError("terminal protocol mismatch")
        if row.get("status") not in (
            "complete",
            "failed",
            "incomplete",
            "budget-exhausted",
        ) or row.get("complete") != (row["status"] == "complete"):
            raise ValueError("invalid terminal status")
        return row
    starts = sorted((directory / "slices").glob("*.started.json"))
    for claim in starts:
        if read(claim)["protocol_sha256"] != digest:
            raise ValueError("slice protocol mismatch")
        if not claim.with_name(claim.name.replace("started", "finished")).exists():
            raise ClaimedWithoutReceipt(str(claim))
        finish = read(claim.with_name(claim.name.replace("started", "finished")))
        if (
            finish["protocol_sha256"] != digest
            or not np.isfinite(finish["elapsed_s"])
            or finish["elapsed_s"] < 0
        ):
            raise ValueError("invalid completed slice accounting")
    elapsed = sum(
        read(p.with_name(p.name.replace("started", "finished")))["elapsed_s"] for p in starts
    )
    if len(starts) >= 12 or elapsed >= 6000:
        row = dict(
            protocol_sha256=digest,
            status="budget-exhausted",
            elapsed_s=elapsed,
            slices=len(starts),
            reason="aggregate cap",
            complete=False,
        )
        append(terminal, row)
        return row
    slot = len(starts) + 1
    begun = clock()
    prefix = directory / "slices" / f"{slot:02}"
    append(
        str(prefix) + ".started.json",
        dict(protocol_sha256=digest, slot=slot, remaining_budget_s=max(0, 6000 - elapsed)),
    )
    deadline = begun + min(500, 6000 - elapsed)
    cache = DurableCache(directory / "points", digest, deadline, clock=clock)
    status, reason, searches = "pending", None, {}
    failures = {}
    try:
        case = loader(plan["binding"])
        if clock() >= deadline:
            raise SliceExpired("loader")
        if case_identity(case) != plan["identity"]:
            raise ValueError("reconstructed physical input mismatch")
        if "imports_path" in plan["binding"]:
            from coarse_import import ImportedEvaluator, read_import

            imported = read_import(
                Path(repository) / plan["binding"]["imports_path"],
                plan["binding"]["imports_sha256"],
            )
            if (
                canonical_digest(imported) != plan["imported_receipts_sha256"]
                or imported["session_id"] != plan["binding"]["session_id"]
            ):
                raise ValueError("coarse import identity mismatch")
            if evaluator_factory is not PointEvaluator:
                raise ValueError("cannot override frozen imported evaluator")
            evaluator = ImportedEvaluator(
                case["observations"], case["bank"], case["prior"], case["tracks"], imported=imported
            )
        else:
            evaluator = evaluator_factory(
                case["observations"], case["bank"], case["prior"], case["tracks"]
            )
        ordinary_bootstrap = evaluator.bootstrap

        def bootstrap(*args, **kwargs):
            point = list(args[3])
            value = cache.fetch(
                ["bootstrap", point], lambda: ordinary_bootstrap(*args, **kwargs), reserve_seconds=5
            )
            return PositionBootstrap(
                tuple(value["satellite_indices"]),
                np.asarray(value["vector"]),
                tuple(BootstrapMatch(**m) for m in value["matches"]),
            )

        evaluator.bootstrap = bootstrap
        config = Hard60Configuration()
        for arm, mode in (
            ("fitted-c", "native"),
            ("zero-c", "native"),
            ("fitted-c", "fixed"),
            ("zero-c", "fixed"),
        ):
            event_index = 0

            def observe(event, arm=arm, mode=mode):
                nonlocal event_index
                if clock() >= deadline:
                    raise SliceExpired("trace replay")
                target = directory / "traces" / (arm + "-" + mode) / f"{event_index:05}.json"
                value = dict(protocol_sha256=digest, event=event)
                if target.exists():
                    if read(target) != value:
                        raise ValueError("resumed search trace differs")
                else:
                    append(target, value)
                event_index += 1

            def evaluate(e, n, arm=arm, mode=mode):
                # Do not claim a point until its separately cached seed is durable.
                if (e, n) not in evaluator.seeds and not getattr(
                    evaluator, "original_failure", lambda point: False
                )((e, n)):
                    evaluator.seeds[(e, n)] = bootstrap(
                        case["observations"],
                        case["bank"],
                        case["prior"],
                        (e, n),
                        case["tracks"],
                        maximum_seconds=5.0,
                        orbit_predictor=predict_orbits,
                    )
                try:
                    row = cache.fetch(["point", e, n, arm], lambda: evaluator(e, n, arm))
                except CachedFailure as error:
                    failures[str((e, n, arm))] = dict(point=[e, n], arm=arm, error=str(error))
                    observe(dict(event="fit-status", east=e, north=n, status="failed"))
                    return 1e100
                observe(
                    dict(
                        event="fit-status",
                        east=e,
                        north=n,
                        status="complete",
                        converged=row.get("fit", {}).get("converged"),
                    )
                )
                return row["scores"][mode]["objective"]

            search = hierarchical_search(
                evaluate,
                radius_km=case["prior"].radius_km,
                levels_km=config.levels_km,
                budget_points=400,
                edge_priority=config.edge_priority,
                observer=observe,
            )
            if arm == "fitted-c" and mode == "native":
                native_parity(search, plan["native_baseline"])
                gate = directory / "native-parity.json"
                value = dict(
                    protocol_sha256=digest, status="verified", count=len(search.evaluations)
                )
                if gate.exists() and read(gate) != value:
                    raise ValueError("native parity receipt mismatch")
                if not gate.exists():
                    append(gate, value)
            searches[arm + ":" + mode] = dict(
                search=search, regions=distinct_basins(search, count=3, minimum_separation_km=12.5)
            )
        if failures:
            status, reason = "incomplete", "one or more point evaluations failed"
        else:
            status = "complete"
    except SliceExpired:
        reason = "slice deadline"
    except Exception as error:
        status, reason = "failed", f"{type(error).__name__}: {error}"
    duration = clock() - begun
    row = dict(
        protocol_sha256=digest,
        status=status,
        reason=reason,
        elapsed_s=elapsed + duration,
        slices=slot,
        complete=status == "complete",
        searches=json_value(searches),
        point_failures=list(failures.values()),
        point_failure_count=len(failures),
    )
    append(
        str(prefix) + ".finished.json",
        dict(protocol_sha256=digest, elapsed_s=duration, status=status, reason=reason),
    )
    if status != "pending":
        append(terminal, row)
    return row
