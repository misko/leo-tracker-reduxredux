"""Build an isolated lag-4 phase-CFO variant from hash-pinned V4 sources."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
NATIVE_REPORT = REPORT / "native"
DEPLOY_NATIVE = Path(
    "/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence"
)
BASE_RECEIPT = NATIVE_REPORT / "libblind_strided_v4.so.build.json"
GENERATED = HERE / "_generated"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"expected exactly one {label} transform anchor")
    return source.replace(old, new, 1)


def generated_sources() -> dict[str, str]:
    coarse = (DEPLOY_NATIVE / "coarse_differential.h").read_text()
    helper = r'''static double complex diff_native_correlation(
    const leo_presence_workspace *w, size_t epoch)
{
    double complex d=0;
    size_t split=w->n-epoch;
    for (size_t k=0; k<split; ++k)
        d+=w->diff_folded[k+epoch]*conj(w->diff_template[k]);
    for (size_t k=split; k<w->n; ++k)
        d+=w->diff_folded[k-split]*conj(w->diff_template[k]);
    return d;
}

'''
    coarse = replace_once(
        coarse,
        "static double diff_native_cell(leo_presence_workspace *w, size_t epoch,\n",
        helper + "static double diff_native_cell(leo_presence_workspace *w, size_t epoch,\n",
        "lag correlation helper",
    )

    presence = (DEPLOY_NATIVE / "presence.c").read_text()
    presence = replace_once(
        presence, "static int grid(", "static int __attribute__((unused)) grid(",
        "unused broad-grid helper",
    )
    presence = replace_once(
        presence, "static void fine_scores(",
        "static void __attribute__((unused)) fine_scores(",
        "unused broad-fine helper",
    )
    old = r'''        double frequencies[1602], scores[1602], coarse_cfo=w->frequencies[f];
        double lower=fmax(-400000,coarse_cfo-80000), upper=fmin(400000,coarse_cfo+80000);
        if (LEO_PRESENCE_POWER_PROPOSAL || proposal_epoch>=0) { lower=-400000; upper=400000; }
        if (LEO_PRESENCE_FAST_FINE_FFT) {
            lower=ceil(lower/w->fine_step_hz)*w->fine_step_hz;
            upper=floor(upper/w->fine_step_hz)*w->fine_step_hz;
        }
        int nf=grid(lower,upper,w->fine_step_hz,frequencies);
        stage_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        fine_scores(w,count,refined,frequencies[0],nf,scores);
        w->profile.acquisition_fft_cpu_ms += clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage_started;
        int best=best_frequency(scores,frequencies,nf);
        double interpolated=frequencies[best];
        if (best>0 && best+1<nf) {
            double curve=scores[best-1]-2*scores[best]+scores[best+1];
            if (isfinite(curve) && curve < -1e-15)
                interpolated += fmax(-w->fine_step_hz,fmin(w->fine_step_hz,
                    0.5*(scores[best-1]-scores[best+1])/curve*w->fine_step_hz));
        }
        nf=grid(fmax(-400000,interpolated-LEO_PRESENCE_CONDITIONED_RADIUS),
            fmin(400000,interpolated+LEO_PRESENCE_CONDITIONED_RADIUS),100,frequencies);
        stage_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        conditioned_scores(w,count,refined,frequencies,nf,scores);
        w->profile.conditioned_cpu_ms += clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage_started;
        best=best_frequency(scores,frequencies,nf);
        c->acquired_cfo_hz=frequencies[best]; c->conditioned_score=scores[best];
'''
    new = r'''        double frequencies[6], scores[6];
        stage_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        double complex phase_correlation=diff_native_correlation(w,(size_t)refined);
        double phase_magnitude=magnitude(phase_correlation);
        double principal=carg(phase_correlation)*w->rate/(TAU*LEO_PRESENCE_DIFFERENTIAL_LAG);
        double alias_period=(double)w->rate/LEO_PRESENCE_DIFFERENTIAL_LAG;
        int first_alias=(int)ceil((-400000.0-principal)/alias_period);
        int last_alias=(int)floor((400000.0-principal)/alias_period);
        int nf=0;
        if (isfinite(phase_magnitude) && phase_magnitude>0 && isfinite(principal)) {
            for (int alias=first_alias; alias<=last_alias; ++alias) {
                double center=principal+alias*alias_period;
                for (int cell=-1; cell<=1; ++cell) {
                    double frequency=fmax(-400000.0,fmin(400000.0,center+100.0*cell));
                    int duplicate=0;
                    for (int prior=0; prior<nf; ++prior)
                        if (frequencies[prior]==frequency) duplicate=1;
                    if (!duplicate && nf<6) frequencies[nf++]=frequency;
                }
            }
        }
        w->profile.acquisition_fft_cpu_ms += clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage_started;
        if (!nf) continue;
        stage_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        conditioned_scores(w,count,refined,frequencies,nf,scores);
        w->profile.conditioned_cpu_ms += clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage_started;
        int best=best_frequency(scores,frequencies,nf);
        c->acquired_cfo_hz=frequencies[best]; c->conditioned_score=scores[best];
'''
    presence = replace_once(presence, old, new, "fine acquisition")

    blind = (NATIVE_REPORT / "blind_strided_v4.c").read_text()
    blind = replace_once(
        blind, '#include "known_state_v3.c"', '#include "presence.c"', "presence include"
    )
    blind += r'''

int leo_phase_cfo_get_profile(const leo_blind_strided_v4_workspace *w,
    leo_presence_profile *profile)
{
    return w && w->dwell ? leo_presence_get_profile(w->dwell->confirm,profile) : -1;
}
'''
    return {
        "coarse_differential.h": coarse,
        "presence.c": presence,
        "blind_phase.c": blind,
    }


def materialize_generated() -> dict[str, str]:
    GENERATED.mkdir(exist_ok=True)
    contents = generated_sources()
    for name, content in contents.items():
        path = GENERATED / name
        if path.exists() and path.read_text() != content:
            raise ValueError(f"generated source drift: {path}")
        path.write_text(content)
    return {str((GENERATED / name).resolve()): sha256(GENERATED / name) for name in contents}


def build(output: Path = HERE / "libphase_cfo.so") -> Path:
    output = output.resolve()
    receipt_path = output.with_name(output.name + ".build.json")
    base = json.loads(BASE_RECEIPT.read_text())
    for source, expected in base["sources_sha256"].items():
        if sha256(Path(source)) != expected:
            raise ValueError(f"parent V4 source drift: {source}")
    generated_hashes = materialize_generated()
    owned = [Path(__file__), HERE / "design.json"]
    sources = {
        **base["sources_sha256"],
        **generated_hashes,
        **{str(path.resolve()): sha256(path) for path in owned},
    }
    if output.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt["sources_sha256"] != sources or sha256(output) != receipt["binary_sha256"]:
            raise ValueError("phase-CFO binary or source differs from receipt")
        return output
    if output.exists() or receipt_path.exists():
        raise ValueError("partial phase-CFO build")
    command = list(base["command"])
    original = str((NATIVE_REPORT / "blind_strided_v4.c").resolve())
    command[command.index(original)] = str((GENERATED / "blind_phase.c").resolve())
    first_include = command.index("-I")
    command[first_include:first_include] = ["-I", str(GENERATED.resolve())]
    command[command.index("-o") + 1] = str(output)
    subprocess.run(command, check=True)
    if generated_hashes != {
        path: sha256(Path(path)) for path in generated_hashes
    }:
        raise ValueError("generated source changed during build")
    receipt = {
        "schema": "org.leo.research.phase-cfo-build/v1",
        "command": command,
        "sources_sha256": sources,
        "binary_sha256": sha256(output),
        "parent_v4_receipt_sha256": sha256(BASE_RECEIPT),
        "semantics": "lag4 phase aliases; offsets -100,0,+100 Hz; unchanged final GLRT",
    }
    with receipt_path.open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return output


if __name__ == "__main__":
    print(build())
