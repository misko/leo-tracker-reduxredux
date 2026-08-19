"""Catalog operation failures with stable, actionable meanings."""


class CatalogError(RuntimeError):
    pass


class CatalogNotFoundError(CatalogError):
    pass


class ActiveRunExistsError(CatalogError):
    pass


class InvalidStateError(CatalogError):
    pass


class LeaseLostError(CatalogError):
    pass


class ProductConflictError(CatalogError):
    pass


class PromotionError(CatalogError):
    pass
