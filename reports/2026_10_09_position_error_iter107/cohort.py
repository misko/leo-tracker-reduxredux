"""Full-cohort runtime reconstruction and exact-key source ports."""

import hashlib
import importlib.util
import json
import runpy
import sys
from pathlib import Path

import numpy as np
from old_coarse_policy import eligibility
from source_plan import compatible, model_identity

from leo.analysis.hard60_bounded_fit import _Problem
from leo.application.hard60_runner import Hard60Configuration
from leo.application.regional_position_runner import json_value
from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PILOT = HERE.parent / "2026_10_09_position_error_iter105"
sys.path.insert(0, str(PILOT))
spec = importlib.util.spec_from_file_location("pilot105_for107", PILOT / "run.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)
HISTORICAL = runpy.run_path(
    str(HERE.parent / "2026_10_09_position_error_iter85/dependencies.py"),
    run_name="import_only",
)


def load_member(member):
    label = member["member"].get("inventory_label", member["member"].get("dataset_label"))
    if member.get("dataset") == "POST18-development":
        source = next((s for s in member["sources"] if s["name"] == "B7"), member["sources"][0])
        document = json.loads((HERE / source["sanitized_path"]).read_text())
        assert (
            hashlib.sha256((HERE / source["sanitized_path"]).read_bytes()).hexdigest()
            == source["sanitized_sha256"]
        )
        observations, bank, prior, tracks, binding = pilot.load_case(document)
        root = Path("/srv/bulk/leo")
        original = document
        baseline = document
    else:
        protocol = json.loads(
            (HERE.parent / "2026_10_09_position_error_iter85/protocol.json").read_text()
        )
        bound = next(
            b
            for b in protocol["members"]
            if b["member"]["session_id"] == member["member"]["session_id"]
        )
        # The immutable85 loader installs82's verified historical protocol adapter.
        # Direct51 imports would leave the ambiguous original lazy `freeze` import.
        case, baseline, _ = HISTORICAL["load"](bound["loader_binding"])
        observations, bank, prior, tracks = (
            case.prepared.observations,
            case.bank,
            case.prior,
            case.prepared.bootstrap_tracks,
        )
        original = case.document
        root = Path(member["raw_input_root"])
        identity = model_identity(original)
        assert not compatible(member["model_identity"], identity)
        assert bank.numbers.tolist() == original["diagnostics"]["bank"]["retained_numbers"]
        archive = pilot.core.TleArchiveReader(Path("/var/lib/leo/tle"))
        snapshot = archive.select_latest_before(case.prepared.start_utc_ns - 505_000_000_000)
        assert snapshot.digest == original["diagnostics"]["snapshot_sha256"]
        payload, _ = pilot.core.exclude_labelled_starlink_debris(archive.read(snapshot))
        catalogue = pilot.core.parse_element_sets(payload)
        indices = [
            i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")
        ]
        evidence = canonical_digest(
            dict(
                windows=case.prepared.evidence_sha256,
                tle=snapshot.digest,
                candidates=[int(catalogue.satellite_numbers[i]) for i in indices],
            )
        )
        assert evidence == original["evidence_sha256"]
        binding = dict(
            input_digest=original["input_manifest_sha256"],
            evidence_digest=original["evidence_sha256"],
            score_signature=canonical_digest(
                dict(prior=json_value(prior), score=json_value(pilot.core.HARD60_SCORE))
            ),
            bank_signature=canonical_digest(bank.numbers.tolist()),
        )
    assert original["session_id"] == member["member"]["session_id"]
    assert canonical_digest(json_value(prior)) == canonical_digest(
        original["configuration"]["prior"]
    )
    assert canonical_digest(json_value(pilot.core.HARD60_SCORE)) == canonical_digest(
        original["configuration"]["scores"]["V16"]
    )
    binding["observation_order_signature"] = canonical_digest(
        dict(
            window_ids=list(observations.window_ids),
            **{
                name: json_value(getattr(observations, name))
                for name in ("times_s", "measured_hz", "rf_hz", "receiver", "channel", "margin")
            },
        )
    )
    required = {
        "application/hard60_runner.py",
        "analysis/hard60_score.py",
        "analysis/regional_position_fit.py",
        "analysis/regional_position_bootstrap.py",
        "analysis/regional_position_calibration.py",
        "application/regional_position_inputs.py",
    }
    names = set(original["configuration"].get("source_digests", {})) | required
    current = {
        name: "sha256:" + hashlib.sha256((ROOT / "src/leo" / name).read_bytes()).hexdigest()
        for name in names
    }
    ordinary = pilot.source_compatibility(original)
    legacy = eligibility(
        original["configuration"].get("source_digests", {}),
        current,
        original["configuration"]["run"],
        json_value(Hard60Configuration()),
    )
    return dict(
        label=label,
        observations=observations,
        bank=bank,
        prior=prior,
        tracks=tracks,
        binding=binding,
        original=original,
        baseline=baseline,
        root=root,
        ordinary_compatibility=ordinary,
        legacy_coarse_eligibility=legacy,
    )


def verify_point(case, basin, value):
    original = value["result"]
    model, fit = pilot.verify_coarse(case["observations"], case["bank"], case["prior"], original)
    point = np.array([float(x) for x in basin.split(":")[1:]])
    np.testing.assert_allclose(fit["vector"][:2], point, atol=1e-9, rtol=0)
    np.testing.assert_allclose(original["bootstrap"]["vector"][:2], point, atol=1e-9, rtol=0)
    vector = np.asarray(fit["vector"])
    assert np.isfinite(vector).all()
    problem = _Problem(model, vector, fixed_position=True, slope_half_width_hz_s=60)
    assert problem.feasible(vector)
    _, gradient, _ = model.evaluate(vector)
    assert np.isfinite(gradient).all(), "Current coarse gradient is nonfinite"
    stationarity = problem.stationarity(vector, gradient)
    if fit["converged"]:
        assert stationarity <= 0.001, "Saved coarse qualification fails current independent KKT"
    return dict(
        objective_verified=True,
        feasible=True,
        stationarity=float(stationarity),
        saved_qualification_verified=bool(fit["converged"]),
    )


class Sources:
    """Current exact stages; the sole optional alias is verified ordinary coarse."""

    def __init__(self, member, case, *, allow_legacy_coarse=False):
        self.member, self.case, self.allow_legacy_coarse = member, case, allow_legacy_coarse
        self.store = RegionalCheckpointStore(
            case["root"],
            member["member"]["session_id"],
            case["original"]["diagnostics"]["checkpoint_binding"],
        )
        self.original_prefix = canonical_digest(case["original"]["configuration"]["run"]) + ":"
        self.audits = {}
        self.failures = []
        self.research = []
        self.metrics = dict(
            get_calls=0,
            coarse_hits=0,
            legacy_coarse_hits=0,
            research_exact_hits=0,
            public_exact_hits=0,
            coarse_rejections=0,
        )
        if member.get("dataset") != "POST18-development":
            module = importlib.util.spec_from_file_location(
                "bound107inputs", HERE.parent / "2026_10_08_hard60_bounded_recovery/inputs.py"
            )
            imported = importlib.util.module_from_spec(module)
            sys.modules[module.name] = imported
            module.loader.exec_module(imported)
            for source in member["sources"]:
                path = source["source"].get("path", "")
                if "2026_10_09_position_error_iter51/regions/" not in path:
                    continue
                document = json.loads((HERE / source["sanitized_path"]).read_text())
                assert (
                    hashlib.sha256((HERE / source["sanitized_path"]).read_bytes()).hexdigest()
                    == source["sanitized_sha256"]
                )
                assert not compatible(model_identity(case["original"]), model_identity(document))
                config = document["configuration"]["run"]
                compatibility = pilot.source_compatibility(
                    dict(
                        document,
                        configuration=dict(
                            document["configuration"], run=dict(config, basin_separation_km=12.5)
                        ),
                    )
                )
                if not compatibility["eligible"]:
                    continue
                directory = (
                    HERE.parent
                    / "2026_10_09_position_error_iter51/local/checkpoints"
                    / case["label"]
                    / source["name"]
                )
                cache = imported.ExperimentCheckpoints(
                    directory, dict(baseline=canonical_digest(case["baseline"]), config=config)
                )
                self.research.append((canonical_digest(config) + ":", cache))

    def get(self, key):
        self.metrics["get_calls"] += 1
        if key.startswith("b7-shared:point:") and key.count(":") == 3:
            eligible = self.case["ordinary_compatibility"]["eligible"] or (
                self.allow_legacy_coarse
                and self.case["legacy_coarse_eligibility"]["metadata_eligible"]
            )
            if not eligible:
                return None
            basin = key.removeprefix("b7-shared:")
            source_key = self.original_prefix + basin
            value = self.store.get(source_key)
            if value is None and self.case["ordinary_compatibility"]["eligible"]:
                # Production B7 stores the shared key directly; ordinary source key may be absent.
                value = self.store.get(key)
                source_key = key
            if not value or not value.get("result"):
                return None
            try:
                audit = verify_point(self.case, basin, value)
            except (AssertionError, ValueError) as error:
                self.failures.append(dict(key=key, reason=repr(error)))
                self.metrics["coarse_rejections"] += 1
                return None
            self.audits[key] = dict(
                source_key=source_key,
                payload_sha256=canonical_digest(value),
                legacy=not self.case["ordinary_compatibility"]["eligible"],
                **audit,
            )
            self.metrics["coarse_hits"] += 1
            self.metrics["legacy_coarse_hits"] += not self.case["ordinary_compatibility"][
                "eligible"
            ]
            return value
        for prefix, cache in self.research:
            if key.startswith(prefix):
                value = cache.get(key)
                if value is not None:
                    self.metrics["research_exact_hits"] += 1
                    return value
        if self.case["ordinary_compatibility"]["eligible"]:
            value = self.store.get(key)
            if value is not None:
                self.metrics["public_exact_hits"] += 1
            return value
        return None
