"""Add one sample of support to each side of the four original wide proposals."""

from .wide_regional import replace

GATE = (
    "    const int scout_radius=wide&&context->receiver_count==2&&\n"
    "        context->refinement_mode==3 ? 2 : 1;"
)


def overlay(source):
    marker = "    int wide=short_window&&context->rate==10000000u;"
    source = replace(source, marker, marker + "\n" + GATE)
    return replace(
        source,
        "            int first=current[c]-1,last=current[c]+1;",
        "            int first=current[c]-scout_radius,last=current[c]+scout_radius;",
    )
