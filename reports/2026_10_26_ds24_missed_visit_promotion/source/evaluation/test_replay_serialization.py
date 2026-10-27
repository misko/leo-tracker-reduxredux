import json
import numpy as np
from replay_endpoints import numpy_encoder


def test_scientific_membership_receipt_serializes_numpy_booleans_arrays_and_counts():
    receipt=dict(compatible=np.bool_(True),count=np.int64(3),values=np.asarray([1.,2.]),nested=[dict(gate=np.bool_(False))])
    result=json.loads(json.dumps(receipt,default=numpy_encoder,allow_nan=False))
    assert result==dict(compatible=True,count=3,values=[1.,2.],nested=[dict(gate=False)])
