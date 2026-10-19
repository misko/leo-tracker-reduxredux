"""Read-only, explicitly past-only catalogue preparation through the archive port."""

from dataclasses import dataclass

from leo.sky.propagation import ElementSetCatalogue, parse_element_sets


@dataclass(frozen=True)
class CausalCatalogue:
    catalogue: ElementSetCatalogue
    provenance: tuple[dict, ...]
    snapshot_count: int


def causal_catalogue(reader, cutoff_utc_ns, *, maximum_age_s=172800.0, provider="space-track"):
    """Newest past element per Starlink in the declared recent archive window.

    Both collection and element epochs must be <= cutoff. No nearest-snapshot
    fallback and no future elements. Age limits bound archive I/O and staleness.
    """
    if maximum_age_s <= 0:
        raise ValueError("positive age limit required")
    oldest = cutoff_utc_ns - int(maximum_age_s * 1e9)
    snapshots = [
        s for s in reader.list_snapshots(provider) if oldest <= s.collected_utc_ns <= cutoff_utc_ns
    ]
    if not snapshots:
        raise ValueError("no past TLE snapshots in declared age window")
    chosen = {}
    for snapshot in snapshots:
        catalogue = parse_element_sets(reader.read(snapshot))
        for name, number, satellite, epoch in zip(
            catalogue.names,
            catalogue.satellite_numbers,
            catalogue.satellites,
            catalogue.element_epoch_utc_ns(),
            strict=True,
        ):
            if "STARLINK" not in name.upper() or not oldest <= epoch <= cutoff_utc_ns:
                continue
            key = (epoch, snapshot.collected_utc_ns, snapshot.sha256)
            if number not in chosen or key > chosen[number][0]:
                chosen[number] = (
                    key,
                    name,
                    satellite,
                    dict(
                        norad=number,
                        name=name,
                        element_epoch_utc_ns=epoch,
                        collected_utc_ns=snapshot.collected_utc_ns,
                        snapshot_digest=snapshot.digest,
                        provider=snapshot.provider,
                        age_s=(cutoff_utc_ns - epoch) / 1e9,
                    ),
                )
    if not chosen:
        raise ValueError("no eligible past Starlink elements")
    numbers = tuple(sorted(chosen))
    return CausalCatalogue(
        ElementSetCatalogue(
            tuple(chosen[n][1] for n in numbers), numbers, tuple(chosen[n][2] for n in numbers)
        ),
        tuple(chosen[n][3] for n in numbers),
        len(snapshots),
    )
