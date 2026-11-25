"""Research overlay for the installed native Normal/Gamma likelihood."""

from contextlib import contextmanager
from ctypes import CDLL, POINTER, c_uint64
import json
from pathlib import Path
import subprocess
from time import process_time_ns
from unittest.mock import patch

from leo.analysis.localization_v4 import native_bound

from tools.pipeline_eval.variants.algo08_posterior_handoff import SOURCE_SHA256, replace


HEADER = Path(__file__).with_suffix(".h")
COUNTS = ("evaluations", "trials", "accepted", "rejected", "stock_replays")


def profiled_source():
    """Replace the convergence update while leaving the pinned posterior intact."""
    path = native_bound.SOURCE
    if native_bound.digest(path) != SOURCE_SHA256:
        raise ValueError("Incompatible installed native likelihood")
    source = replace(path.read_text(), "/* All work belongs", HEADER.read_text() + "\n/* All work belongs")
    source = replace(source, "int nb_run(", "static int gamma_run(")
    source = replace(source, "6*(size_t)k*sz+13*(size_t)k", "(7+2*GAMMA_MEMORY)*(size_t)(k+t)+6*(size_t)k*sz+13*(size_t)k")
    source = replace(source, "double *row_f=row+(l->qmax?l->qmax:1);", """
    double *row_f=row+(l->qmax?l->qmax:1);
    GammaOptimizer opt={.n=k+t, .scale=row_f+sz};
    opt.x=opt.scale+opt.n;
    opt.gradient=opt.x+opt.n;
    opt.last_x=opt.gradient+opt.n;
    opt.last_gradient=opt.last_x+opt.n;
    opt.ordinary=opt.last_gradient+opt.n;
    opt.direction=opt.ordinary+opt.n;
    opt.steps=opt.direction+opt.n;
    opt.changes=opt.steps+GAMMA_MEMORY*opt.n;
    for (int g=0;g<k;g++) opt.scale[g]=sqrt(2.*alpha[g]);
    for (int j=0;j<t;j++) opt.scale[k+j]=sqrt(2.*pa[j]);
    """)
    source = replace(source, "for(int iteration=0;iteration<=budget;iteration++) {", """
    for(int iteration=0;iteration<=budget;iteration++) {
        if (!((iteration>0) && change<1e-5) && (iteration==budget || iteration==GAMMA_LIMIT)) {
            code=NB_UNSUPPORTED;
            goto done;
        }
        ++gamma_counts[GAMMA_EVALUATIONS];
    """)
    source = replace(source, "        if(final)break;", """
        if(final)break;
        double objective=logdet, log_prior_det=0.;
        for (int j=0;j<p;j++) log_prior_det+=log(precision[j]);
        objective=fmax(0.,objective-log_prior_det);
        for (int j=0;j<p;j++) objective+=precision[j]*mean[j]*mean[j];
        for (int g=0;g<k;g++) {
            double ratio=rate[g]/beta0;
            objective+=power[g]*weight[g]*energy[g]+fmax(0.,2.*alpha[g]*(log(ratio)+1./ratio-1.));
        }
        for (int j=0;j<t;j++) {
            double ratio=v0/v[j];
            objective+=fmax(0.,2.*pb0*v0*(log(ratio)+1./ratio-1.));
        }
        if (!isfinite(objective)) {code=NB_NONFINITE;goto done;}
    """)
    source = replace(source, ";rate[g]=next_rate[g];}", ";}")
    source = replace(source, ";prate[j]=next_prate[j];}", ";}")
    source = replace(source, "        performed++;", """
        gamma_next(&opt,k,t,rate,prate,next_rate,next_prate,beta0,pb0,objective,&change,iteration);
        performed++;
    """)
    source += """
int nb_profiled_gamma(void *layout,void *pf,void *ps,void *pi,void *pc,
 const double *y,const double *u,const double *sigma,const int64_t *groups,
 const double *power,const int64_t *prior,int t,const double *alpha,const double *pa,
 double beta0,double pb0,double v0,int budget,double min_rcond,
 double *mean,double *native,double *weight,double *precision,double *v,double *scalars,
 int *updates,double *returned_rates) {
    int code=gamma_run(layout,pf,ps,pi,pc,y,u,sigma,groups,power,prior,t,alpha,pa,
                       beta0,pb0,v0,budget,min_rcond,mean,native,weight,precision,v,
                       scalars,updates,returned_rates);
    if (code) ++gamma_counts[GAMMA_REPLAYS];
    return code;
}
"""
    return source


def build(output):
    source = profiled_source()
    output = Path(output)
    generated = output.with_suffix(".c")
    generated.write_text(source)
    flags = [*native_bound.FLAGS, "-Wall", "-Wextra", "-Werror"]
    subprocess.run(["cc", *flags, str(generated), "-lm", "-o", str(output)],
                   check=True, timeout=30)
    output.with_suffix(".json").write_text(json.dumps(dict(
        pinned_source_sha256=SOURCE_SHA256, header_sha256=native_bound.digest(HEADER),
        generated_sha256=native_bound.digest(generated), binary_sha256=native_bound.digest(output),
        compiler_flags=flags), indent=2) + "\n")


def operations(library, *, allowed=None, activity=None):
    library = Path(library)
    manifest = json.loads(library.with_suffix(".json").read_text())
    if native_bound.digest(library) != manifest["binary_sha256"]:
        raise ValueError("Incompatible Gamma build manifest")
    binary = CDLL(str(library))
    counts = binary.nb_profiled_gamma_counts
    counts.argtypes, counts.restype = [POINTER(c_uint64)], None

    def read():
        out = (c_uint64 * len(COUNTS))()
        counts(out)
        return dict(zip(COUNTS, out, strict=True))

    def wrap(bound):
        stock = bound.run
        run = binary.nb_profiled_gamma
        run.argtypes, run.restype = stock.argtypes, stock.restype

        def call(*args):
            if allowed is not None and not allowed():
                if activity is not None:
                    activity["ordinary_grid_bypasses"] += 1
                return stock(*args)
            if activity is None:
                status = run(*args)
                return stock(*args) if status else status
            began = process_time_ns()
            status = run(*args)
            activity["profiled_call_cpu_ns"] += process_time_ns() - began
            activity["profiled_calls"] += 1
            if not status:
                return status
            began = process_time_ns()
            replay = stock(*args)
            activity["stock_replay_cpu_ns"] += process_time_ns() - began
            return replay

        call.argtypes, call.restype = stock.argtypes, stock.restype
        bound.run = call
        return bound

    return wrap, read


@contextmanager
def profiled_gamma(algo08_position, library, *, allowed=None, activity=None):
    """Scope the numerical change to the saved solve's native backend."""
    wrap, read = operations(library, allowed=allowed, activity=activity)
    backend = algo08_position.NativeBound
    instances, stats = [], {}
    before = read()

    def factory(*args, **kwargs):
        bound = backend(*args, **kwargs)
        instances.append(bound)
        return wrap(bound)

    try:
        with patch.object(algo08_position, "NativeBound", factory):
            yield stats
    finally:
        stats.update({key: count - before[key] for key, count in read().items()})
        for bound in instances:
            for key, count in bound.counts.items():
                stats[key] = stats.get(key, 0) + count
            bound.clear()
