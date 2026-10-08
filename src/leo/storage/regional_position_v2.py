"""Hard60 has its own immutable publication namespace."""

from leo.contracts.regional_position_v2 import RegionalPositionManifestV2, RegionalPositionStatusV2
from leo.storage.regional_position import _RegionalPositionStore


class Hard60Store(_RegionalPositionStore[RegionalPositionStatusV2, RegionalPositionManifestV2]):
    namespace = "scanner-regional-position-v2"
    methods = ("V16",)
    status_model = RegionalPositionStatusV2
    manifest_model = RegionalPositionManifestV2
