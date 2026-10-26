"""Small finite-trial one-sided bounds; no fitted detection thresholds."""
import math


def binomial_upper(k,n,alpha=.05):
    if not 0<=k<=n or n<=0:raise ValueError('nonempty valid trial counts required')
    if k==n:return 1.
    if k==0:return 1-alpha**(1/n)
    def cdf(p):
        logs=[math.lgamma(n+1)-math.lgamma(j+1)-math.lgamma(n-j+1)+j*math.log(p)+(n-j)*math.log1p(-p)
            for j in range(k+1)]
        maximum=max(logs)
        return math.exp(maximum)*sum(math.exp(v-maximum)for v in logs)
    lo=k/n;hi=1-1e-15
    for _ in range(70):
        mid=(lo+hi)/2
        if cdf(mid)>alpha:lo=mid
        else:hi=mid
    return (lo+hi)/2


def independent_mean_upper(k,n,alpha=.05):
    """KL-Chernoff bound for average independent, possibly unequal Bernoulli p."""
    if not 0<=k<=n or n<=0:raise ValueError('nonempty valid trial counts required')
    if k==n:return 1.
    if k==0:return 1-alpha**(1/n)
    q=k/n;target=-math.log(alpha)/n
    def divergence(p):return q*math.log(q/p)+(1-q)*math.log((1-q)/(1-p))
    lo=q;hi=1-1e-15
    for _ in range(70):
        mid=(lo+hi)/2
        if divergence(mid)<target:lo=mid
        else:hi=mid
    return (lo+hi)/2
