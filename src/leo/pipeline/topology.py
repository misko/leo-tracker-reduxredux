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

_PATH_STAGE = ("path-standard", ResourceClass.HEAVY, IqAccess.RECEIVER_PATH)


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
        stage_key, resource_class, iq_access = _PATH_STAGE
        node_id = f"path-{path_ordinal:02d}-standard"
        jobs.append(
            JobNodeV1(
                node_id=node_id,
                stage_key=stage_key,
                scope=scope,
                iq_access=iq_access,
                resource_class=resource_class,
            )
        )
        path_terminals.setdefault(scope.stream_id, []).append(node_id)

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
