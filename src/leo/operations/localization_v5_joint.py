"""Bind paired joint scheduling to the native backend and publish actual work."""

from copy import deepcopy

from leo.analysis.localization_v5.joint_schedule import JointSchedule, JointScheduleFailure
from leo.contracts.digests import canonical_digest
from leo.contracts.localization_v5 import (
    joint_schedule_counts,
    validate_joint_schedule_policy,
    validate_joint_schedule_work,
)


class JointScheduleFactory:
    def __init__(self, backend, policy):
        self._backend = backend
        self._policy = deepcopy(validate_joint_schedule_policy(policy))
        self._binding = canonical_digest(backend.manifest)
        self._experiments = []

    @property
    def policy(self):
        return deepcopy(self._policy)

    def identity(self):
        if canonical_digest(self._backend.manifest) != self._binding:
            raise JointScheduleFailure('Native joint-schedule manifest binding changed')
        return self._binding

    def __call__(self, context, optimizer):
        schedule = JointSchedule(context, optimizer, self._backend, self.identity)
        self._experiments.append(schedule)
        return schedule

    def provenance(self):
        self.identity()
        rows = [s.snapshot() for s in self._experiments]
        return validate_joint_schedule_work(dict(
            schema_version=1, policy=self.policy, backend_manifest_sha256=self._binding,
            experiments=rows, counts=joint_schedule_counts(rows)), self._policy, self._binding)
