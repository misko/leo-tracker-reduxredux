"""Read earlier sealed orbit indexes after the regional Satrec handoff repair."""

from portable_orbit_index import UnsupportedExport, versions


LEGACY_SOURCE_INDEX = "c73739b9fea3b950312b83dfc0f7e4d0a3d5c4c924cfc29d8a3c72b0967ad58a"
REPAIRED_SOURCE_INDEX = "b1d43a1593d25e6232dd8c37b0e548015ca19de10359c43c22e483fb3f8285fe"


def compatible_versions(current, producer):
    """Allow only the audited constructor relocation, with every other pin unchanged."""
    if current == producer:
        return current
    current_hashes = current["source_sha256"]
    if current_hashes["source_index"] == REPAIRED_SOURCE_INDEX:
        # These two whole-file versions have identical SourceIndex,
        # VerifiedIndexReader, export_supported and phase_history definitions.
        previous = dict(current, source_sha256=dict(current_hashes, source_index=LEGACY_SOURCE_INDEX))
        if previous == producer:
            return previous
    raise UnsupportedExport("The sealed producer is incompatible with the installed orbit reader")


def producer_versions(producer):
    return compatible_versions(versions(), producer)
