from run_annotation_phase_audit import select


def test_phase_audit_prioritizes_candidates_then_ds24_and_preserves_claims():
    def row(i,points,scope='DS24',**kw):return dict(track_id=i,points=str(points),scopes=scope,state='conditionally_supported_identity',**kw)
    rows=[row('a',100),row('b',90,phase_audit_source='done'),row('c',10,'automatic'),row('d',1000),row('e',80),row('f',2000,'automatic')]
    members={r['track_id']:True for r in rows};members['d']=False
    assert [r['track_id'] for r in select(rows,members,{'c'},{'a'},3)]==['c','e','f']
    assert [r['track_id'] for r in select(rows,members,{'c'},{'a'},1)]==['c']
