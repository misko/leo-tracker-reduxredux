"""One bounded, resumable trajectory/TLE pipeline for both scan modes."""

import time
from datetime import UTC, datetime
from typing import Protocol

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.persistent_hop_tle_match import (
    PersistentHopTleMatchConfig,
    match_persistent_hop_track_to_tles,
)
from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    PersistentHopTrajectoryInputError,
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.persistent_hop_tracking import PersistentHopTrackingService, _GroupWork
from leo.application.persistent_hop_trajectory import PersistentHopTrajectoryProjectionError
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.scanner_tracking import (
    ScannerTrackingInputs,
    ScannerTrackingProductV1,
    ScannerTrackingStatusV1,
)
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.sky.propagation import count_element_sets


class TrackingProducts(Protocol):
    def status(self, session_id: str) -> ScannerTrackingStatusV1: ...
    def save(self, status: ScannerTrackingStatusV1) -> None: ...
    def put_artifact(self, session_id, name, payload): ...
    def publish(self, product: ScannerTrackingProductV1) -> None: ...


class ScannerTrackingService:
    def __init__(
        self,
        *,
        inputs: ScannerTrackingInputs,
        products: TrackingProducts,
        tle_archive,
        observer_site: ObserverSiteV1,
        renderer,
        matcher=match_persistent_hop_track_to_tles,
        clock=time.monotonic,
    ):
        self.inputs, self.products, self.archive = inputs, products, tle_archive
        self.site, self.renderer, self.matcher, self.clock = observer_site, renderer, matcher, clock

    def run(self, session_id: str, *, maximum_seconds: float = 180, group_limit: int = 4):
        if not 0 < maximum_seconds <= 1800 or not 1 <= group_limit <= 32:
            raise ValueError("tracking work bounds are invalid")
        started = self.clock()
        status = self.products.status(session_id)
        if status.state == "complete":
            return status
        source = self.inputs.load(session_id)
        trajectory_config = PersistentHopTrajectoryConfig()
        policy_digest = canonical_digest(
            {
                "algorithm": "scanner-shared-tracking-v1",
                "trajectory": trajectory_config.digest,
                "group_limit": group_limit,
                "selection": "eligible-first-longest-support-v1",
                "catalogue": "exclude-labelled-starlink-debris-before-response-v1",
                "observer": self.site.model_dump(mode="json"),
            }
        )
        product = status.product or ScannerTrackingProductV1(
            session_id=session_id,
            capture_mode=source.capture_mode,
            sample_rate_hz=source.sample_rate_hz,
            input_manifest_sha256=source.input_manifest_sha256,
            analysis_manifest_sha256=source.analysis_manifest_sha256,
            configuration_digest=policy_digest,
            created_at=datetime.now(UTC),
            trajectory_state="unsupported",
            tle_state="pending",
            observer_site=self.site,
            group_limit=group_limit,
        )
        if (
            product.input_manifest_sha256 != source.input_manifest_sha256
            or product.analysis_manifest_sha256 != source.analysis_manifest_sha256
            or product.configuration_digest != policy_digest
        ):
            raise ValueError("tracking checkpoint authority or policy changed")

        def save(phase):
            self.products.save(
                ScannerTrackingStatusV1(
                    session_id=session_id, state="running", phase=phase, product=product
                )
            )

        save("trajectory")
        try:
            candidates = project_scanner_candidates(source)
            trajectory = reconstruct_persistent_hop_trajectories(
                candidates, config=trajectory_config
            )
        except (PersistentHopTrajectoryProjectionError, PersistentHopTrajectoryInputError) as error:
            product = product.model_copy(
                update={
                    "trajectory_state": "unsupported"
                    if isinstance(error, PersistentHopTrajectoryProjectionError)
                    else "no-trajectory",
                    "tle_state": "unavailable",
                    "reasons": (str(error),),
                }
            )
            self.products.publish(product)
            return self.products.status(session_id)
        config = PersistentHopTleMatchConfig(
            selection_protocol_digest=policy_digest, nominal_rf_hz=trajectory_config.canonical_rf_hz
        )
        product = product.model_copy(update={"tle_match_config_digest": config.digest})
        work, total = eligible_groups(trajectory, config)
        selected = work[:group_limit]
        if not product.artifacts:
            ref = self.products.put_artifact(
                session_id,
                "trajectory",
                self.renderer(trajectory, candidates, (), catalogue_diagnostics=False),
            )
            product = product.model_copy(
                update={
                    "trajectory_state": "complete",
                    "projected_candidate_count": len(candidates),
                    "physical_group_count": total,
                    "eligible_group_count": len(work),
                    "deferred_group_count": len(work),
                    "tracklets": tuple(
                        PersistentHopTrackingService._tracklet_summary(t)
                        for t in trajectory.tracklets
                    ),
                    "artifacts": (ref,),
                }
            )
        save("tle-matching")
        if selected:
            try:
                earliest = min(c.support_start_utc_ns for c in candidates)
                snapshot = self.archive.select_latest_before(earliest - 505_000_000_000)
                raw = self.archive.read(snapshot)
                original = TleSnapshotRefV1(
                    provider=snapshot.provider,
                    collected_utc_ns=snapshot.collected_utc_ns,
                    digest=snapshot.digest,
                    object_count=count_element_sets(raw),
                )
                payload, exclusions = exclude_labelled_starlink_debris(raw)
                eligible = original.model_copy(
                    update={
                        "digest": sha256_digest(payload.encode("ascii")),
                        "object_count": count_element_sets(payload),
                    }
                )
                if product.original_tle_snapshot and product.original_tle_snapshot != original:
                    raise ValueError("causal catalogue changed while resuming")
                product = product.model_copy(
                    update={
                        "original_tle_snapshot": original,
                        "eligible_tle_snapshot": eligible,
                        "catalogue_exclusions": exclusions,
                    }
                )
                save("tle-matching")
            except Exception as error:
                product = product.model_copy(
                    update={
                        "tle_state": "unavailable",
                        "reasons": (f"{type(error).__name__}: {error}",),
                    }
                )
                self.products.publish(product)
                return self.products.status(session_id)
            completed = {c.physical_group_id for c in product.tle_candidates} | {
                c.physical_group_id for c in product.unscored_groups
            }
            for item in selected:
                if item.group.group_id in completed:
                    continue
                if self.clock() - started >= maximum_seconds:
                    save("tle-matching")
                    return self.products.status(session_id)
                try:
                    result = self.matcher(
                        persistent_hop_tracklet_graph(
                            item.hypothesis, item.representative.tracklet_id
                        ),
                        payload,
                        tle_snapshot=eligible,
                        observer_site=self.site,
                        config=config,
                    )
                    product = product.model_copy(
                        update={
                            "tle_candidates": (
                                *product.tle_candidates,
                                PersistentHopTrackingService._candidate_summary(item, result),
                            )
                        }
                    )
                except Exception as error:
                    product = product.model_copy(
                        update={
                            "unscored_groups": (
                                *product.unscored_groups,
                                PersistentHopTrackingService._unscored(
                                    item, f"{type(error).__name__}: {error}"
                                ),
                            )
                        }
                    )
                product = product.model_copy(
                    update={
                        "attempted_group_count": product.attempted_group_count + 1,
                        "deferred_group_count": product.deferred_group_count - 1,
                    }
                )
                save("tle-matching")
        state = (
            "no-eligible-groups"
            if not selected
            else "partial"
            if product.tle_candidates and product.unscored_groups
            else "unavailable"
            if product.unscored_groups
            else "complete"
        )
        ref = self.products.put_artifact(
            session_id,
            "trajectory-tle",
            self.renderer(trajectory, candidates, product.tle_candidates),
        )
        product = product.model_copy(
            update={"tle_state": state, "artifacts": (*product.artifacts, ref)}
        )
        self.products.publish(product)
        return self.products.status(session_id)


def eligible_groups(trajectory, config):
    by_id = {t.tracklet_id: t for t in trajectory.tracklets}
    work, total = [], 0
    for rank, hypothesis in enumerate(trajectory.hypotheses, 1):
        for group in hypothesis.physical_groups:
            total += 1
            eligible = []
            for tid in group.tracklet_ids:
                tracklet = by_id[tid]
                graph = persistent_hop_tracklet_graph(hypothesis, tid)
                span = (
                    max(o.support_end_utc_ns for o in graph.observations)
                    - min(o.support_start_utc_ns for o in graph.observations)
                ) / 1e9
                if (
                    len(graph.observations) >= config.minimum_support_observations
                    and span >= config.minimum_support_span_s
                ):
                    eligible.append(tracklet)
            if eligible:
                representative = max(
                    eligible,
                    key=lambda t: (t.end_utc_ns - t.start_utc_ns, len(t.points), t.tracklet_id),
                )
                work.append(_GroupWork(rank, hypothesis, group, representative))
    work.sort(
        key=lambda w: (
            w.hypothesis_rank,
            -(w.representative.end_utc_ns - w.representative.start_utc_ns),
            -len(w.representative.points),
            w.group.group_id,
        )
    )
    return tuple(work), total
