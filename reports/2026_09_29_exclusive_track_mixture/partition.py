import itertools
import math
import numpy as np


class Partition:
    def __init__(self,groups):
        n=len(groups);sets=list(map(set,groups))
        adjacency=[{j for j in range(n) if j!=i and not sets[i].isdisjoint(sets[j])} for i in range(n)]
        self.edges=sum(map(len,adjacency))//2
        unseen=set(range(n));self.components=[]
        while unseen:
            todo=[min(unseen)];unseen.remove(todo[0]);indices=[]
            while todo:
                i=todo.pop();indices.append(i)
                for j in sorted(adjacency[i]&unseen):
                    unseen.remove(j);todo.append(j)
            indices=sorted(indices)
            if len(indices)>12:
                raise ValueError('Exact component limit exceeded')
            rows=[]
            for bits in itertools.product((0.,1.),repeat=len(indices)):
                active=[i for i,b in zip(indices,bits,strict=True) if b]
                if all(j not in adjacency[i] for i,j in itertools.combinations(active,2)):
                    rows.append(bits)
            self.components.append((np.array(indices),np.array(rows)))
        self.n=n
        self.prior_logz=self.evaluate(np.full(n,math.log(4)))[0]

    def evaluate(self,log_activity):
        log_activity=np.asarray(log_activity,dtype=float)
        assert log_activity.shape==(self.n,) and np.isfinite(log_activity).all()
        value=0.;marginal=np.zeros(self.n)
        for indices,states in self.components:
            scores=states@log_activity[indices]
            normal=np.logaddexp.reduce(scores)
            marginal[indices]=np.exp(scores-normal)@states
            value+=float(normal)
        return value,marginal

    def density(self,signal,background):
        background=np.asarray(background)
        z,weights=self.evaluate(math.log(4)+np.asarray(signal)-background)
        return float(background.sum()+z-self.prior_logz),weights
