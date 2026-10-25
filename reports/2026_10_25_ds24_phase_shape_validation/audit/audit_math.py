"""Independent saved-array factorial arithmetic; no model/propagation imports."""
import numpy as np


def factorial(v11, v10, v01, v00):
    """P=phase deviation, S=shape deviation; return all three estimands.

    Input vectors are endpoint minus the same artificial truth in east/north km.
    The norm and squared-norm contrasts are not vector interactions transformed
    afterward: each applies its own scalar functional to the four endpoints.
    """
    v11, v10, v01, v00 = [np.asarray(v, float) for v in (v11,v10,v01,v00)]
    if any(v.shape != (2,) or not np.isfinite(v).all() for v in (v11,v10,v01,v00)):
        raise ValueError('four finite east/north error vectors required')
    vector = v11-v10-v01+v00
    norm = np.linalg.norm(v11)-np.linalg.norm(v10)-np.linalg.norm(v01)+np.linalg.norm(v00)
    squared = v11@v11-v10@v10-v01@v01+v00@v00
    a,b = v10-v00,v01-v00
    additive = v00+a+b
    square_identity = 2*a@b+2*additive@vector+vector@vector
    return dict(vector_interaction_km=vector.tolist(),
                vector_interaction_norm_km=float(np.linalg.norm(vector)),
                scalar_error_interaction_km=float(norm),
                squared_error_interaction_km2=float(squared),
                squared_interaction_additive_cross_term_km2=float(2*a@b),
                squared_interaction_vector_remainder_km2=float(2*additive@vector+vector@vector),
                squared_identity_error=float(abs(squared-square_identity)))


def observation_interaction(y11,y10,y01,y00):
    arrays=[np.asarray(v,float) for v in (y11,y10,y01,y00)]
    if len({a.shape for a in arrays})!=1 or not all(np.isfinite(a).all() for a in arrays):
        raise ValueError('matched finite native-ID arrays required')
    return arrays[0]-arrays[1]-arrays[2]+arrays[3]
