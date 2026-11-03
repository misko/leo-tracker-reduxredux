def select(track_rows):
    """Bounded seeded greedy closures, ranked only by training coverage."""
    by_id={r['track_id']:r for r in track_rows}
    assert len(by_id)==len(track_rows)
    for row in track_rows:
        assert len(row['groups'])==len(set(row['groups']))
    ranked=sorted(by_id,key=lambda k:(-by_id[k]['training_count'],k))
    alternatives={}
    for seed in [None,*ranked]:
        used=set();chosen=[]
        if seed is not None:
            chosen.append(seed);used.update(by_id[seed]['groups'])
        for k in ranked:
            if k==seed:
                continue
            groups=set(by_id[k]['groups'])
            if used.isdisjoint(groups):
                chosen.append(k);used.update(groups)
        ids=tuple(sorted(chosen))
        alternatives[ids]=sum(by_id[k]['training_count'] for k in ids)
    best=min(alternatives,key=lambda ids:(-alternatives[ids],ids))
    return dict(track_ids=list(best),training_count=alternatives[best],alternatives=[dict(track_ids=list(k),training_count=v) for k,v in sorted(alternatives.items())])
