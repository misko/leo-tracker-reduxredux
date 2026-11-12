"""Immutable ALGO07v5 results in their own persisted namespace."""

from leo.contracts import localization_v5
from leo.storage.localization_v3 import LocalizationV3Store


class LocalizationV5Store(LocalizationV3Store):
    contract = localization_v5
    namespace = "localization-v5-v1"
