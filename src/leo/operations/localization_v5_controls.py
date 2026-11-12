"""Own native identity validation and account for actual control-cache invocations."""

from copy import deepcopy

from leo.analysis.localization_v5.control_reuse import CompleteControlCache
from leo.contracts.digests import canonical_digest
from leo.contracts.localization_v5 import (
    validate_inclusion_control_policy,
    validate_inclusion_control_work,
)


class ControlCacheFactory:
    def __init__(self, backend, policy):
        self._backend = backend
        self._policy = deepcopy(validate_inclusion_control_policy(policy))
        self._binding = canonical_digest(backend.manifest)
        self._invocations = []

    @property
    def policy(self):
        return deepcopy(self._policy)

    def identity(self):
        if canonical_digest(self._backend.manifest) != self._binding:
            raise RuntimeError('Native control-cache manifest binding changed')
        return self._binding

    def __call__(self):
        cache = CompleteControlCache(self._backend, self.identity)
        self._invocations.append(cache)
        return cache

    def provenance(self):
        self.identity()
        rows = [cache.counts() for cache in self._invocations]
        keys = ('requests', 'computed', 'reused', 'failed', 'unkeyable', 'in_progress')
        return validate_inclusion_control_work(dict(
            schema_version=1, policy=self.policy, backend_manifest_sha256=self._binding,
            invocations=rows, counts={key: sum(row[key] for row in rows) for key in keys}),
            self._policy, self._binding)
