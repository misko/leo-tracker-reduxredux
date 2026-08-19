"""Manifest-authoritative subject topology for Standard pipeline expansion."""

from __future__ import annotations

from dataclasses import dataclass

from leo.contracts.digests import canonical_digest
from leo.contracts.recording import RecordingManifestV1
from leo.pipeline.contracts import ResourceClass
from leo.pipeline.planning import (
    ExpandedRunPlanV1,
    IqAccess,
    JobDependencyRefV1,
    JobNodeV1,
)
from leo.pipeline.scopes import ScopeIdentityV1

_PATH_STAGES = (
    ("path-input-bind", ResourceClass.STREAMING, IqAccess.NONE),
    ("path-quality", ResourceClass.STREAMING, IqAccess.RECEIVER_PATH),
    ("path-power", ResourceClass.STREAMING, IqAccess.RECEIVER_PATH),
    ("path-waterfall", ResourceClass.HEAVY, IqAccess.RECEIVER_PATH),
    ("path-probe-schedule", ResourceClass.CPU, IqAccess.NONE),
    ("path-pilot-scan", ResourceClass.HEAVY, IqAccess.RECEIVER_PATH),
    ("path-trajectory-bank", ResourceClass.MEMORY, IqAccess.NONE),
    ("path-trajectory-feedback", ResourceClass.HEAVY, IqAccess.RECEIVER_PATH),
    ("path-scientific-report", ResourceClass.CPU, IqAccess.NONE),
    ("path-presentation", ResourceClass.CPU, IqAccess.NONE),
)

_PATH_EDGE_SLOTS = (
    (1, 0),  # input bind -> quality
    (2, 1),  # quality -> power
    (3, 2),  # power -> waterfall
    (4, 0),  # input bind -> deterministic probe schedule
    (5, 4),  # schedule -> pilot scan
    (6, 5),  # pilot observations -> trajectory bank
    (7, 5),  # exact pilot observations -> IQ correction/re-detection
    (7, 6),  # selected trajectories -> IQ correction/re-detection
    (8, 0),  # exact input binding -> terminal scientific report
    (8, 1),  # quality -> terminal scientific report
    (8, 2),  # power -> terminal scientific report
    (8, 3),  # waterfall -> terminal scientific report
    (8, 4),  # exact probe schedule -> terminal scientific report
    (8, 5),  # exact pilot observations -> terminal scientific report
    (8, 6),  # trajectory bank -> terminal scientific report
    (8, 7),  # feedback and its trajectory-table output -> scientific report
    (9, 2),  # power source arrays -> bounded presentation
    (9, 3),  # waterfall source arrays -> bounded presentation
    (9, 5),  # pilot/constellation source arrays -> bounded presentation
    (9, 6),  # trajectory family inventory -> bounded presentation
    (9, 7),  # corrected detection arrays -> bounded presentation
    (9, 8),  # report identity/summary -> bounded presentation
)


@dataclass(frozen=True, slots=True)
class CompiledScopeInventory:
    receiver_paths: tuple[ScopeIdentityV1, ...]
    radios: tuple[ScopeIdentityV1, ...]
    paired: ScopeIdentityV1 | None
    synchronization_inventory_digest: str

    @property
    def scopes(self) -> tuple[ScopeIdentityV1, ...]:
        return self.receiver_paths + self.radios + (() if self.paired is None else (self.paired,))


def synchronization_inventory_document(manifest: RecordingManifestV1) -> list[dict[str, object]]:
    ordered = sorted(manifest.streams, key=lambda item: (item.stream_id, item.radio.radio_id))
    identities = tuple((item.stream_id, item.radio.radio_id) for item in ordered)
    if len(set(identities)) != len(identities):
        raise ValueError("manifest repeats a stream/radio topology identity")
    if len({item.stream_id for item in ordered}) != len(ordered):
        raise ValueError("manifest repeats a stream identity")
    if len({item.radio.radio_id for item in ordered}) != len(ordered):
        raise ValueError("manifest repeats a radio identity")
    return [
        {
            "ordinal": ordinal,
            "stream_id": stream.stream_id,
            "radio": {
                "radio_id": stream.radio.radio_id,
                "serial": stream.radio.serial,
                "uri": stream.radio.uri,
                "transport": stream.radio.transport.value,
            },
            "receiver_ids": list(
                (stream.applied_settings or stream.requested_settings).receiver_ids
            ),
            "sample_rate_hz": (stream.applied_settings or stream.requested_settings).sample_rate_hz,
            "captured_sample_count": stream.captured_sample_count,
            "timing": None if stream.timing is None else stream.timing.model_dump(mode="json"),
            "state": stream.state.value,
        }
        for ordinal, stream in enumerate(ordered)
    ]


def compile_scope_inventory(manifest: RecordingManifestV1) -> CompiledScopeInventory:
    inventory_digest = canonical_digest(synchronization_inventory_document(manifest))
    paths: list[ScopeIdentityV1] = []
    radios: list[ScopeIdentityV1] = []
    for stream in sorted(manifest.streams, key=lambda item: (item.stream_id, item.radio.radio_id)):
        settings = stream.applied_settings or stream.requested_settings
        radios.append(
            ScopeIdentityV1.radio(
                session_id=manifest.session_id,
                stream_id=stream.stream_id,
                radio_id=stream.radio.radio_id,
            )
        )
        paths.extend(
            ScopeIdentityV1.receiver_path(
                session_id=manifest.session_id,
                stream_id=stream.stream_id,
                receiver_id=receiver_id,
            )
            for receiver_id in settings.receiver_ids
        )
    return CompiledScopeInventory(
        receiver_paths=tuple(paths),
        radios=tuple(radios),
        paired=(
            None
            if len(manifest.streams) != 2
            else ScopeIdentityV1.paired(
                session_id=manifest.session_id,
                synchronization_inventory_digest=inventory_digest,
            )
        ),
        synchronization_inventory_digest=inventory_digest,
    )


def compile_standard_run_plan(
    manifest: RecordingManifestV1, *, manifest_digest: str, pipeline_release_id: str
) -> ExpandedRunPlanV1:
    """Expand every authoritative path, radio and optional pair into one exact DAG."""

    topology = compile_scope_inventory(manifest)
    jobs: list[JobNodeV1] = []
    edges: list[JobDependencyRefV1] = []
    path_terminals: dict[str, list[str]] = {}
    for path_ordinal, scope in enumerate(topology.receiver_paths):
        assert scope.stream_id is not None
        path_nodes: list[str] = []
        for stage_ordinal, (stage_key, resource_class, iq_access) in enumerate(_PATH_STAGES):
            node_id = f"path-{path_ordinal:02d}-stage-{stage_ordinal:02d}"
            jobs.append(
                JobNodeV1(
                    node_id=node_id,
                    stage_key=stage_key,
                    scope=scope,
                    iq_access=iq_access,
                    resource_class=resource_class,
                )
            )
            path_nodes.append(node_id)
        edges.extend(
            JobDependencyRefV1(
                job_node_id=path_nodes[consumer],
                depends_on_job_node_id=path_nodes[producer],
            )
            for consumer, producer in _PATH_EDGE_SLOTS
        )
        path_terminals.setdefault(scope.stream_id, []).append(path_nodes[8])

    radio_nodes: list[str] = []
    for radio_ordinal, scope in enumerate(topology.radios):
        assert scope.stream_id is not None
        node_id = f"radio-{radio_ordinal:02d}-reduce"
        jobs.append(
            JobNodeV1(
                node_id=node_id,
                stage_key="radio-scientific-report",
                scope=scope,
                iq_access=IqAccess.NONE,
                resource_class=ResourceClass.CPU,
            )
        )
        for dependency in sorted(path_terminals[scope.stream_id]):
            edges.append(
                JobDependencyRefV1(
                    job_node_id=node_id,
                    depends_on_job_node_id=dependency,
                )
            )
        radio_nodes.append(node_id)

    if topology.paired is not None:
        node_id = "paired-00-reduce"
        jobs.append(
            JobNodeV1(
                node_id=node_id,
                stage_key="paired-scientific-report",
                scope=topology.paired,
                iq_access=IqAccess.NONE,
                resource_class=ResourceClass.CPU,
            )
        )
        edges.extend(
            JobDependencyRefV1(job_node_id=node_id, depends_on_job_node_id=dependency)
            for dependency in sorted(radio_nodes)
        )
    return ExpandedRunPlanV1.create(
        session_id=manifest.session_id,
        manifest_digest=manifest_digest,
        pipeline_release_id=pipeline_release_id,
        jobs=tuple(jobs),
        edges=tuple(edges),
    )
