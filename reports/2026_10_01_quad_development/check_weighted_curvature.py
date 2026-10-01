"""Recorded-state candidate-weighted curvature checks; no optimization."""
import time
import fcntl
from pathlib import Path
import sys
import numpy as np
from run_association_ambiguity import HERE,source,baseline,sealed,digest,verify_sources,save
from run_marginal_pilot import marginal_setup
from marginal_visibility_port import normalized_mass
from weighted_candidate_curvature import candidate_blocks
from epoch_block_curvature import solve_blocks


def main():
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        rows=[];inputs={}
        for unit in ['DS9-B01-S1','DS10-B01-D1','DS11-B01-Q']:
            started=time.monotonic();receipt,bindings=source(unit);inputs.update(bindings)
            original,_,_=baseline(unit);model=marginal_setup(unit,original)
            state=np.asarray(receipt['best']['mean']);_,g,_=model.evaluate(state)
            begin=time.monotonic()
            blocks=[candidate_blocks(p,state[c]) for p,c in zip(model.ports,model.columns,strict=True)]
            d=-solve_blocks(model.precision,model.columns,blocks,g);direction_seconds=time.monotonic()-begin
            # Independently evaluate H*d through whitened residual Jacobian actions,
            # without using assembled candidate blocks or the Schur elimination.
            action=model.precision*d
            for p,c in zip(model.ports,model.columns,strict=True):
                _,prob=normalized_mass(p.score_all(state[c]))
                batch=p.original.linearize_candidates(state[c],np.arange(p.candidate_count))
                residual=p.observation[None,:]-batch['means'];precision=p.likelihood.precision
                q=np.einsum('ni,ij,nj->n',residual,precision,residual)
                weights=prob[:-1]*(4+residual.shape[1])/(4+q)
                local=np.column_stack([np.broadcast_to(d[c[:5]],(p.candidate_count,5)),d[c[5:]]])
                projected=np.einsum('nmc,nc->nm',batch['jacobians'],local)
                compact=np.einsum('nmc,nm->nc',batch['jacobians'],projected@precision.T)*weights[:,None]
                action[c[:5]]+=np.sum(compact[:,:5],axis=0);action[c[5:]]+=compact[:,5]
            relative=float(np.linalg.norm(action+g)/max(np.linalg.norm(g),1.))
            assert relative<1e-7,(unit,relative)
            slope=float(g@d);assert slope<0,(unit,slope)
            dense_error=None
            if original['binding']['size']==1:
                matrix=np.diag(model.precision)
                for c,localblocks in zip(model.columns,blocks,strict=True):
                    for i,block in enumerate(localblocks):
                        indices=np.r_[c[:5],c[5+i]];matrix[np.ix_(indices,indices)]+=block
                reference=-np.linalg.solve(matrix,g)
                dense_error=float(np.linalg.norm(d-reference)/max(np.linalg.norm(reference),1.))
                assert dense_error<1e-7,(unit,dense_error)
            rows.append(dict(unit=unit,dimensions=len(state),tracks=len(model.ports),relative_system_residual=relative,
                relative_dense_direction_error=dense_error,slope=slope,direction_seconds=direction_seconds,seconds=time.monotonic()-started))
            print(rows[-1],flush=True)
        sources={str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
            if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])}
        verify_sources(inputs)
        save(HERE/'weighted-curvature-check-v1.json',dict(rows=rows,inputs=inputs,source_sha256=sources,
            qualification='Three fixed recorded states. Residual curvature approximation only; direct Jacobian system-action check, dense single-window solve, descent check. No fit or geographic scoring.'))


if __name__=='__main__':main()
