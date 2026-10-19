from probe_ds23_joint_family_search import joint_operations


def test_joint_search_keeps_nonbest_alternatives_and_failed_singles():
    singles=[dict(source=i,target=10+i*2+j,valid=j==0,loss=float(j+i),
                  changes=[dict(row_index=i,candidate_index=10+i*2+j,alias=0)])
             for i in range(4) for j in range(2)]
    operations=joint_operations(singles)
    assert len(operations)==72  # 6*4 pairs + 4*8 triples + 16 quadruples
    assert {len(op) for op in operations}=={2,3,4}
    assert any(all(c['candidate_index']%2==1 for c in op) for op in operations if len(op)==4)
    assert all(len({c['row_index'] for c in op})==len(op) for op in operations)


def test_no_spurious_joint_with_one_family():
    assert joint_operations([dict(source=0,target=1,valid=True,loss=1.,changes=[])])==[]
