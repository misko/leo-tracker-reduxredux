import ctypes
import subprocess

from tools.pipeline_eval.qualification import native_pruning_build as build
from tools.pipeline_eval.qualification import native_pruning_eval as trial

C_WITNESS = """
#include "native_pruning.h"

int witness(void) {
    enum {width=18, stride=24, bins=21};
    float sums[width*stride];
    int32_t support[width];
    double grid[width*bins];
    for (int i=0;i<width*stride;++i) sums[i]=7;
    for (int i=0;i<width;++i) support[i]=88;
    for (int i=0;i<width*bins;++i) grid[i]=99;
    const int active[]={0,2,3,4,11,width-1};
    const int bad[][2]={{1,1},{7,1},{0,18},{-1,5}};
    if (!leo_pruning_valid(NULL,0,width) || leo_pruning_valid(NULL,1,width) ||
        leo_pruning_valid(active,16,width)) return 0;
    for (size_t i=0;i<sizeof(bad)/sizeof(*bad);++i)
        if (leo_pruning_valid(bad[i],2,width)) return 0;
    if (!leo_pruning_valid(active,6,width)) return 0;
    leo_pruning_clear(sums,support,stride,active,6);
    for (int epoch=0;epoch<width;++epoch) {
        int selected=0;
        for(int i=0;i<6;++i) selected|=epoch==active[i];
        if (support[epoch]!=(selected ? 0 : 88)) return 0;
        for (int f=0;f<stride;++f)
            if (sums[epoch*stride+f]!=(selected ? 0 : 7)) return 0;
    }
    for (int i=0;i<6;++i) {
        int epoch=active[i];
        support[epoch]=i;
        for (int f=0;f<stride;++f) sums[epoch*stride+f]=(float)(17+f)/(float)9;
    }
    leo_pruning_publish(grid,sums,support,width,bins,stride,active,6);
    for (int f=0;f<bins;++f) for(int epoch=0;epoch<width;++epoch) {
        int selected=0, observable=0;
        for (int i=0;i<6;++i) {
            selected|=epoch==active[i];
            observable|=epoch>=active[i]-1 && epoch<=active[i]+1;
        }
        double expected=99;
        if (observable) expected=(selected && support[epoch]) ?
            (double)sums[epoch*stride+f]/support[epoch] : -INFINITY;
        if (grid[f*width+epoch]!=expected) return 0;
    }
    /* A previous positive cell must be reset when it is now only a neighbor. */
    const int changed[]={10,12};
    leo_pruning_clear(sums,support,stride,changed,2);
    leo_pruning_publish(grid,sums,support,width,bins,stride,changed,2);
    for (int f=0;f<bins;++f) if (grid[f*width+11]!=-INFINITY) return 0;
    return 1;
}
"""


def test_sparse_read_set_matches_dense_and_never_uses_old_neighbors(tmp_path):
    c = tmp_path / "witness.c"
    out = tmp_path / "witness.so"
    c.write_text(C_WITNESS)
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-O3",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fPIC",
            "-shared",
            "-I",
            str(build.HEADER.parent),
            str(c),
            "-o",
            str(out),
        ],
        check=True,
    )
    assert ctypes.CDLL(str(out)).witness() == 1


def test_overlay_dispatch_requires_the_exact_live_geometry():
    short = "    if (coarse(w,count,NULL)) return -1;\n    out.coarse_cpu_ms=after();"
    target = build.full(short)
    assert "w->n == 13333 && count == 200000" in target
    assert "regional_epochs == w->regional_epochs" in target
    assert "leo_pruning_valid(regional_epochs, regional_count" in target
    assert " : coarse(w,count,NULL)" in target


def test_parity_includes_read_set_and_ignores_clocks():
    science = {"target": False, "gains": [1, 0], "active": [[0, 1], [9, 10]], "sha256": "a"}
    control = {"science": science, "clocks": {"cpu_ns": 10}}
    candidate = {"science": science, "clocks": {"cpu_ns": 5}}
    assert trial.exact(dict(control=control, candidate=candidate))
    for changed in ({"target": True}, {"active": [[0, 1], [10]]}, {"sha256": "b"}):
        assert not trial.exact(
            dict(control=control, candidate=candidate | {"science": science | changed})
        )
