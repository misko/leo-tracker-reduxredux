"""Bind fixed labels to scan-local physical satellite identities."""
def group_keys(scan_ids, catalogues, track_counts, labels):
    if not len(scan_ids) == len(catalogues) == len(track_counts): raise ValueError('scan binding lengths')
    if len(set(scan_ids)) != len(scan_ids) or sum(track_counts) != len(labels): raise ValueError('invalid scan/track binding')
    output = []; offset = 0
    for scan_id, catalogue, count in zip(scan_ids, catalogues, track_counts):
        for i in labels[offset:offset+count]:
            if not 0 <= i <= len(catalogue): raise ValueError('invalid label')
            output.append((scan_id, int(catalogue[i])) if i < len(catalogue) else None)
        offset += count
    return output
