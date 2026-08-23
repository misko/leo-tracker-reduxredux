"""Catalog operation failures with stable, actionable meanings."""


class CatalogError(RuntimeError):
    pass


class CatalogNotFoundError(CatalogError):
    pass


class ActiveRunExistsError(CatalogError):
    pass


class IdenticalRunExistsError(ActiveRunExistsError):
    """A scientifically identical pending, running, or successful run exists."""

    def __init__(self, *, run_id: str, state: str, pipeline_lane: str) -> None:
        self.run_id = run_id
        self.state = state
        self.pipeline_lane = pipeline_lane
        super().__init__(
            f"identical {pipeline_lane} analysis run already exists in {state} state: {run_id}"
        )


class InvalidStateError(CatalogError):
    pass


class LeaseLostError(CatalogError):
    pass


class ProductConflictError(CatalogError):
    pass


class PromotionError(CatalogError):
    pass
