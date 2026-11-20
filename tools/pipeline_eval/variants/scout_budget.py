"""Extend only the wide prepared-fractional short-window differential scout."""

from pathlib import Path

from .wide_regional import replace

HEADER = Path(__file__).with_name("scout_budget_centers.h")


def proposal_core(source):
    marker = "static void emit_ints("
    source = replace(source, marker, '#include "scout_budget_centers.h"\n' + marker)
    old = "    int centers[4],int *center_count,leo_proposal_timing *timing){"
    new = "    int *centers,int budget,int *center_count,leo_proposal_timing *timing){"
    source = replace(source, old, new, count=2)
    old = "    if(!w||!raw||!centers||!center_count)return -1;"
    new = "    if(!w||!raw||!centers||!center_count||(budget!=4&&budget!=16))return -1;"
    source = replace(source, old, new, count=2)
    source = replace(source, "int leo_proposal_top4(", "int leo_proposal_ranked(")
    source = replace(source, "int leo_proposal_top4_single(", "int leo_proposal_ranked_single(")
    source = replace(
        source,
        "    *center_count=top4_linear(b->scores[4],z,n,centers,b->ranking);",
        "    *center_count=budget==4 ? top4_linear(b->scores[4],z,n,centers,b->ranking) :\n"
        "        scout_budget_centers(b->scores[4],z,n,centers,b->ranking,b->rank_scratch);",
        count=2,
    )
    marker = "#else\nint main(int argc,char **argv){"
    wrappers = """int leo_proposal_top4(leo_proposal_workspace *w,const int16_t *raw,
    size_t start,int rx,
    int centers[4],int *count,leo_proposal_timing *timing)
{
    return leo_proposal_ranked(w,raw,start,rx,centers,4,count,timing);
}
int leo_proposal_top4_single(leo_proposal_workspace *w,const int16_t *raw,size_t start,
    int centers[4],int *count,leo_proposal_timing *timing)
{
    return leo_proposal_ranked_single(w,raw,start,centers,4,count,timing);
}
"""
    return replace(source, marker, wrappers + marker)


def proposal_header(source):
    return replace(
        source,
        "#endif",
        """__attribute__((visibility("hidden")))
int leo_proposal_ranked(leo_proposal_workspace *workspace,const int16_t *raw,
    size_t start,int receiver,int *centers,int budget,int *count,leo_proposal_timing *timing);
__attribute__((visibility("hidden")))
int leo_proposal_ranked_single(leo_proposal_workspace *workspace,const int16_t *raw,
    size_t start,int *centers,int budget,int *count,leo_proposal_timing *timing);
#endif""",
    )


def namespace(source):
    return replace(
        source,
        "#define leo_proposal_create",
        """#define leo_proposal_ranked leo_native_glrt_private_proposal_ranked
#define leo_proposal_ranked_single leo_native_glrt_private_proposal_ranked_single
#define leo_proposal_create""",
    )


def native(source):
    source = replace(
        source,
        "    int wide=short_window&&context->rate==10000000u;",
        "    int wide=short_window&&context->rate==10000000u;\n"
        "    const int budget=wide&&context->refinement_mode==3 ? 16 : 4;",
    )
    source = replace(source, "int (*centers)[2][4]", "int (*centers)[2][16]")
    source = replace(source, "int current[4]={0}", "int current[16]={0}")
    source = replace(source, "        if(count>4)count=4;", "        if(count>budget)count=budget;")
    first = source.index("    for(size_t window=0;window<windows;++window){")
    last = source.index("    measured.proposals_cpu_ms", first)
    proposal = source[first:last]
    proposal = replace(proposal, "leo_proposal_top4_single", "leo_proposal_ranked_single")
    proposal = replace(proposal, "leo_proposal_top4(", "leo_proposal_ranked(")
    proposal = replace(
        proposal,
        "centers[anchor][rx],&counts[anchor][rx]",
        "centers[anchor][rx],budget,&counts[anchor][rx]",
        count=2,
    )
    return source[:first] + proposal + source[last:]


def apply(source):
    edits = {
        "native_glrt.c": native,
        "kernel/private/proposal_core.c": proposal_core,
        "kernel/private/proposal_core.h": proposal_header,
        "kernel/private_namespace.h": namespace,
    }
    for name, edit in edits.items():
        target = source / name
        target.write_text(edit(target.read_text()))
    (source / "kernel/private" / HEADER.name).write_bytes(HEADER.read_bytes())
