"""Research-only safeguarded Anderson iteration for a complete native likelihood."""

import ctypes as ct
import subprocess
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants.algo08_posterior_handoff import SOURCE_SHA256, replace


def build(output):
    original = native_bound.SOURCE
    if native_bound.digest(original) != SOURCE_SHA256:
        raise ValueError("Expected the released native likelihood source")
    header = Path(__file__).with_suffix(".h").read_text()
    source = replace(original.read_text(), "/* All work belongs", header + "\n/* All work belongs")
    source = replace(source, "    Layout *l=pointer;\n    if(!l || !pf", """
    memset(aa_counts,0,sizeof(aa_counts));
    Layout *l=pointer;
    if(!l || !pf""")
    source = replace(source, "3*sz+(l->qmax?l->qmax:1);",
                     "3*sz+(l->qmax?l->qmax:1)+(2*AA_HISTORY+2)*(size_t)(k+t);")
    source = replace(source, "    /* Current group Gram/RHS", """
    double *images=row_f+sz,*residuals=images+(size_t)AA_HISTORY*(k+t);
    double *proposal=residuals+(size_t)AA_HISTORY*(k+t);
    Anderson estimator={k,t,0,0,0.,images,residuals,proposal,proposal+k+t};
    /* Current group Gram/RHS""")
    source = replace(source, "        int final=(iteration==budget", """
        if(iteration==budget && !(change<1e-5)){code=AA_REPLAY;goto done;}
        aa_counts[AA_EVALUATED]++;
        int final=(iteration==budget""")
    for rate, index in (("rate", "g"), ("prate", "j")):
        boundary = f"if(z>change)change=z;{rate}[{index}]=next_{rate}[{index}];}}"
        source = replace(source, boundary, "if(z>change)change=z;}")
    source = replace(source, "        performed++;", """
        performed++;
        sequence(&estimator,rate,prate,next_rate,next_prate,beta0,pb0,&change,budget-iteration-1);
    """)
    generated = output.with_suffix(".c")
    with generated.open("x") as stream:
        stream.write(source)
    subprocess.run(["cc", *native_bound.FLAGS, "-Wall", "-Wextra", "-Werror",
                    str(generated), "-lm", "-o", str(output)], timeout=30, check=True)


@contextmanager
def accelerated(owner, library):
    binary = ct.CDLL(str(library))
    reference = owner.run
    compiled = binary.nb_run
    compiled.argtypes, compiled.restype = reference.argtypes, reference.restype
    readout = binary.nb_anderson_counts
    readout.argtypes, readout.restype = [ct.POINTER(ct.c_int)], None
    metrics = Counter()

    def run(*args):
        metrics["native_calls"] += 1
        status = compiled(*args)
        values = (ct.c_int * 4)()
        readout(values)
        metrics.update(dict(zip(("trials", "accepted", "rejected", "evaluations"),
                                values, strict=True)))
        if status:
            metrics["cold_replays"] += 1
            return reference(*args)
        return status

    with patch.object(owner, "run", run):
        yield metrics
