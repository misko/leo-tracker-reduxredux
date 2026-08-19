"""Create-only confined storage for operational WP11 campaign plans."""

from __future__ import annotations

import json
import os
import re
import stat
from contextlib import suppress
from uuid import uuid4

from leo.application.frequency_calibration import ImmutableDocumentRefV1
from leo.application.wp11_operations import WP11CampaignPlanV1, wp11_run_id
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage import PinnedLocalRoot

_MAX_PLAN_BYTES = 2 * 1024 * 1024
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class WP11PlanConflict(RuntimeError):
    pass


class ImmutableWP11PlanStore:
    def __init__(self, qualification_root: PinnedLocalRoot) -> None:
        self._root = qualification_root.clone()
        self._plans = self._root.child("wp11-plans", create=True)
        self._runs = self._root.child("wp11-plan-runs", create=True)
        self._bound_workflow: object | None = None
        self._authority = object()

    def close(self) -> None:
        self._runs.close()
        self._plans.close()
        self._root.close()

    def _bind_production_workflow(self, workflow: object) -> object:
        from leo.application.wp11_production import WP11ProductionWorkflow

        if (
            type(workflow) is not WP11ProductionWorkflow
            or getattr(workflow, "_plans", None) is not self
        ):
            raise TypeError("WP11 plan store binds only its production workflow")
        if self._bound_workflow is not None and self._bound_workflow is not workflow:
            raise RuntimeError("WP11 plan store is already bound to another workflow")
        self._bound_workflow = workflow
        return self._authority

    def _publish_authoritative(
        self,
        authority: object,
        workflow: object,
        plan: WP11CampaignPlanV1,
    ) -> ImmutableDocumentRefV1:
        if authority is not self._authority or workflow is not self._bound_workflow:
            raise PermissionError("WP11 plan publication requires bound production authority")
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
        return plan, _ref(campaign_id, payload)

    def load_for_run(
        self, run_id: str
    ) -> tuple[WP11CampaignPlanV1, ImmutableDocumentRefV1]:
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
