"""Common-sample known-pilot linear models; no acquisition or identity inference."""
import numpy as np

FS=5_000_000
TS=4.4e-6


def design(times, epoch_samples, cfo_hz, frequencies_hz, pilot, roll=0):
    local=np.asarray(times)-epoch_samples/FS
    symbol=np.floor(local/TS).astype(int)
    within=local-symbol*TS
    valid=(symbol>=2)&(symbol<=301)
    safe=np.clip(symbol-2,0,299)
    codes=np.roll(pilot,roll,axis=0)[safe]
    matrix=codes*np.exp(2j*np.pi*(within[:,None]*np.asarray(frequencies_hz)[None,:]+local[:,None]*cfo_hz))
    matrix[~valid]=0
    interior=valid&(within>=.8e-6)&(within<=3.6e-6)
    return matrix,interior&(symbol>=22)&(symbol<=221),interior&(symbol>=222)


def compare(samples, matrices, training, held):
    assert np.sum(training)>=512 and np.sum(held)>=256
    assert not np.any(training&held)
    y=np.asarray(samples)
    denominator=float(np.sum(abs(y[held])**2))
    assert denominator>0
    results={}
    for name,matrix in matrices.items():
        coefficients,_,rank,singular=np.linalg.lstsq(matrix[training],y[training],rcond=1e-10)
        prediction=matrix[held]@coefficients
        results[name]=dict(held_nmse=float(np.sum(abs(y[held]-prediction)**2)/denominator),
                          training_nmse=float(np.sum(abs(y[training]-matrix[training]@coefficients)**2)/np.sum(abs(y[training])**2)),
                          columns=matrix.shape[1],rank=int(rank),
                          condition=float(singular[0]/singular[-1]) if singular[-1]>0 else None)
    return results
