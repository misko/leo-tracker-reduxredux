"""B7 publication in a separate immutable namespace."""

from leo.contracts.regional_position_v3 import RegionalPositionManifestV3, RegionalPositionStatusV3
from leo.storage.regional_position import _RegionalPositionStore


class B7Store(_RegionalPositionStore[RegionalPositionStatusV3, RegionalPositionManifestV3]):
    namespace = "scanner-regional-position-v3"
    methods = ("V16",)
    status_model = RegionalPositionStatusV3
    manifest_model = RegionalPositionManifestV3
