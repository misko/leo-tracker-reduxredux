"""Local conditional design projection, not an observed covariance."""
import numpy as np
def project(jacobian,height,weights):
    root=np.sqrt(weights);a=jacobian*root[:,None];b=height*root
    coefficient,_,rank,singular=np.linalg.lstsq(a,b,rcond=1e-10)
    residual=b-a@coefficient;energy=float(b@b)
    return dict(compensation_per_km_height=coefficient.tolist(),rank=int(rank),singular_values=singular.tolist(),
                retained_height_information_fraction=float(residual@residual/energy) if energy else None)
