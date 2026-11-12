"""Immutable native ALGO07v4 results in their own persisted namespace."""

from leo.contracts import localization_v4
from leo.storage.localization_v3 import LocalizationV3Store


class LocalizationV4Store(LocalizationV3Store):
    contract = localization_v4
    namespace = "localization-v4-v1"
