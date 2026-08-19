"""Create-only confined storage for operational WP11 campaign plans."""

from __future__ import annotations

import json
import os
import re
import stat
import weakref
from contextlib import suppress
from typing import cast
from uuid import uuid4

from leo.application.frequency_calibration import ImmutableDocumentRefV1
from leo.application.wp11_operations import (
    WP11CampaignPlanV1,
    WP11CaptureAuthorityPort,
    WP11PlanMemberV1,
    wp11_legacy_receipt_name,
    wp11_run_id,
)
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.scientific import MatchedPilotAcceptanceConfigV1
from leo.qualification.scientific_campaign import campaign_config_from_accepted_capture
from leo.storage import PinnedLocalRoot

_MAX_PLAN_BYTES = 2 * 1024 * 1024
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_WORKFLOW_REGISTRY: dict[
    int,
    tuple[
        weakref.ReferenceType[object],
        weakref.ReferenceType[object],
        weakref.ReferenceType[object],
        str,
    ],
] = {}


class WP11PlanConflict(RuntimeError):
    pass


class ImmutableWP11PlanStore:
    def __init__(self, qualification_root: PinnedLocalRoot) -> None:
        self._root = qualification_root.clone()
        self._plans = self._root.child("wp11-plans", create=True)
        self._runs = self._root.child("wp11-plan-runs", create=True)

    def close(self) -> None:
        _WORKFLOW_REGISTRY.pop(id(self), None)
        self._runs.close()
        self._plans.close()
        self._root.close()

    def _bind_production_workflow(
        self,
        workflow: object,
        capture_authority: object,
        pipeline_release_id: str,
    ) -> None:
        from leo.application.trusted_campaign import ImmutableCaptureCampaignAuthority
        from leo.application.wp11_production import WP11ProductionWorkflow

        if (
            type(workflow) is not WP11ProductionWorkflow
            or getattr(workflow, "_plans", None) is not self
            or type(capture_authority) is not ImmutableCaptureCampaignAuthority
            or getattr(workflow, "_capture", None) is not capture_authority
            or getattr(workflow, "_pipeline_release_id", None) != pipeline_release_id
        ):
            raise TypeError("WP11 plan store binds only its production workflow")
        existing = _WORKFLOW_REGISTRY.get(id(self))
        if existing is not None and existing[1]() is not workflow:
            raise RuntimeError("WP11 plan store is already bound to another workflow")

        key = id(self)

        def discard(_reference: weakref.ReferenceType[object]) -> None:
            current = _WORKFLOW_REGISTRY.get(key)
            if current is not None and (current[0]() is None or current[1]() is None):
                _WORKFLOW_REGISTRY.pop(key, None)

        _WORKFLOW_REGISTRY[key] = (
            weakref.ref(self, discard),
            weakref.ref(workflow),
            weakref.ref(capture_authority),
            pipeline_release_id,
        )

    def _publish_authoritative(
        self,
        workflow: object,
        *,
        campaign_id: str,
        capture: ImmutableDocumentRefV1,
        processing_config: MatchedPilotAcceptanceConfigV1,
    ) -> ImmutableDocumentRefV1:
        registered = _WORKFLOW_REGISTRY.get(id(self))
        if (
            registered is None
            or registered[0]() is not self
            or registered[1]() is not workflow
            or registered[2]() is None
        ):
            raise PermissionError("WP11 plan publication requires bound production authority")
        capture_authority = cast(WP11CaptureAuthorityPort, registered[2]())
        pipeline_release_id = registered[3]
        if processing_config.detector_binding.pipeline_release != pipeline_release_id:
            raise ValueError("WP11 processing config differs from the deployed pipeline release")
        receipt = capture_authority.resolve(capture)
        campaign = campaign_config_from_accepted_capture(
            campaign_id=campaign_id,
            capture_receipt=receipt,
            detector_binding=processing_config.detector_binding,
        )
        plan = WP11CampaignPlanV1.create(
            campaign_id=campaign_id,
            capture=capture,
            pipeline_release_id=pipeline_release_id,
            processing_config=processing_config,
            members=tuple(
                WP11PlanMemberV1(
                    ordinal=index,
                    inventory=item,
                    legacy_receipt_name=wp11_legacy_receipt_name(campaign_id, index),
                )
                for index, item in enumerate(campaign.capture_inventory)
            ),
        )
        payload = canonical_json_bytes(plan.model_dump(mode="json"))
        if len(payload) > _MAX_PLAN_BYTES:
            raise ValueError("WP11 plan exceeds bounded publication size")
        name = f"{plan.campaign_id}.json"
        self._publish_leaf(self._plans, name, payload, plan.campaign_id)
        session_ids = tuple(dict.fromkeys(item.inventory.session_id for item in plan.members))
        for session_id in session_ids:
            run_id = wp11_run_id(plan.campaign_id, session_id)
            binding = canonical_json_bytes(
                {
                    "campaign_id": plan.campaign_id,
                    "plan_digest": plan.plan_digest,
                    "session_id": session_id,
                    "run_id": run_id,
                }
            )
            self._publish_leaf(self._runs, f"{run_id}.json", binding, run_id)
        return _ref(plan.campaign_id, payload)

    def _publish_leaf(
        self,
        directory: PinnedLocalRoot,
        name: str,
        payload: bytes,
        identity: str,
    ) -> None:
        temporary = f".{identity}.{uuid4().hex}.partial"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory.fileno(),
        )
        try:
            offset = 0
            while offset < len(payload):
                offset += os.write(descriptor, payload[offset:])
            os.fsync(descriptor)
            os.fchmod(descriptor, 0o440)
        finally:
            os.close(descriptor)
        try:
            try:
                os.link(
                    temporary,
                    name,
                    src_dir_fd=directory.fileno(),
                    dst_dir_fd=directory.fileno(),
                    follow_symlinks=False,
                )
            except FileExistsError:
                if self._read_at(directory, name) != payload:
                    raise WP11PlanConflict(
                        f"WP11 immutable binding conflicts with existing ID: {identity}"
                    ) from None
            os.fsync(directory.fileno())
        finally:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=directory.fileno())

    def load(self, campaign_id: str) -> tuple[WP11CampaignPlanV1, ImmutableDocumentRefV1]:
        _require_safe_id(campaign_id)
        payload = self._read_at(self._plans, f"{campaign_id}.json")
        plan = WP11CampaignPlanV1.model_validate_json(payload)
        if plan.campaign_id != campaign_id:
            raise ValueError("WP11 plan content differs from requested campaign")
        if plan.pipeline_release_id != plan.processing_config.detector_binding.pipeline_release:
            raise ValueError("WP11 plan contains inconsistent pipeline release identities")
        return plan, _ref(campaign_id, payload)

    def load_for_run(self, run_id: str) -> tuple[WP11CampaignPlanV1, ImmutableDocumentRefV1]:
        _require_safe_id(run_id)
        binding = self._read_at(self._runs, f"{run_id}.json")
        value = json.loads(binding)
        if not isinstance(value, dict):
            raise ValueError("WP11 run binding is not an object")
        campaign_id = value.get("campaign_id")
        session_id = value.get("session_id")
        if not isinstance(campaign_id, str) or not isinstance(session_id, str):
            raise ValueError("WP11 run binding lacks exact string identities")
        plan, ref = self.load(campaign_id)
        if (
            value.get("run_id") != run_id
            or value.get("plan_digest") != plan.plan_digest
            or wp11_run_id(campaign_id, session_id) != run_id
            or not any(item.inventory.session_id == session_id for item in plan.members)
        ):
            raise ValueError("WP11 run binding differs from immutable campaign plan")
        return plan, ref

    def _read_at(self, directory: PinnedLocalRoot, name: str) -> bytes:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory.fileno())
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o440
                or info.st_nlink != 1
            ):
                raise ValueError("WP11 plan lacks immutable file semantics")
            size = info.st_size
            if size <= 0 or size > _MAX_PLAN_BYTES:
                raise ValueError("WP11 plan size is invalid")
            payload = b""
            while len(payload) < size:
                block = os.read(descriptor, size - len(payload))
                if not block:
                    break
                payload += block
            if len(payload) != size:
                raise ValueError("WP11 plan changed during read")
            return payload
        finally:
            os.close(descriptor)


def _ref(campaign_id: str, payload: bytes) -> ImmutableDocumentRefV1:
    return ImmutableDocumentRefV1(
        logical_uri=f"qualification://wp11-plans/{campaign_id}.json",
        digest=sha256_digest(payload),
    )


def _require_safe_id(value: str) -> None:
    if not _SAFE_ID.fullmatch(value):
        raise ValueError("WP11 identifier is unsafe for immutable storage")
