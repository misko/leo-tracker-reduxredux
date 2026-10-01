"""Full marginal window score; argmax labels are diagnostics, not conditioning."""
import numpy as np
from shared_window_objective import WindowObjective


class MarginalWindowObjective(WindowObjective):
    def evaluate(self,state,assigned=None,gradient=True):
        state=np.asarray(state,dtype=float)
        if state.shape!=self.precision.shape or not np.all(np.isfinite(state)):raise ValueError('invalid state')
        if np.linalg.norm(state[:2])>self.radius:raise ValueError('outside geographic prior')
        # The existing optimizer passes labels back with an accepted trial. They
        # must never turn this marginal objective into a conditioned objective.
        if assigned is not None and len(assigned)!=len(self.ports):raise ValueError('diagnostic label length mismatch')
        value=float(.5*(self.precision*state)@state);g=self.precision*state if gradient else None;labels=[]
        for port,columns in zip(self.ports,self.columns,strict=True):
            local=state[columns]
            if gradient:
                score,local_gradient=port.marginal_score_gradient(local);g[columns]-=local_gradient
            else:score=port.marginal_score(local)
            value-=score;labels.append(int(np.argmax(port.score_all(local))))
        if not np.isfinite(value) or (gradient and not np.all(np.isfinite(g))):raise ValueError('nonfinite marginal objective')
        return value,g,tuple(labels)
