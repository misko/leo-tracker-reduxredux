static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <math.h>
#include <stdio.h>

int main(void)
{
    const double threshold=.025;
    assert(boundary_margin_allowed(2.0*threshold,0.0));
    assert(boundary_margin_allowed(threshold,0.0));
    assert(!boundary_margin_allowed(nextafter(threshold,0.0),0.0));
    assert(boundary_margin_allowed(nextafter(threshold,INFINITY),0.0));
    assert(boundary_margin_allowed(NAN,1.0));
    assert(boundary_margin_allowed(INFINITY,1.0));
    assert(boundary_margin_allowed(1.0,INFINITY));
    puts("boundary margin .025 passed: finite, equal threshold, nextafter, and nonfinite fallback");
    return 0;
}
