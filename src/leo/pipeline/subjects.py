"""Run-bound manifest subject evidence exposed through a narrow analyzer port."""

from __future__ import annotations

from typing import Protocol

from leo.contracts.standard_pipeline import StandardPairInputBindV2, StandardPathInputBindV2
from leo.pipeline.scopes import ScopeIdentityV1


class SubjectBindingReader(Protocol):
    """Resolve immutable subject facts from one already-verified analysis run.

    A concrete reader is bound by composition to the run's retained raw-integrity
    capability, manifest digest, exact release/configuration identities, capture
    lineage, and calibration resolver. An analyzer supplies only its persisted
    scope; it never supplies storage paths or authority digests.
    """

    def receiver_path(self, scope: ScopeIdentityV1) -> StandardPathInputBindV2: ...

    def paired(self, scope: ScopeIdentityV1) -> StandardPairInputBindV2: ...
