#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

#include "source/native/adaptive/detector/kernel/private/interval_bounds_layout.h"

static void test_shape(size_t epochs, size_t capacity)
{
    assert(epochs > 0 && capacity > 0);
    size_t cells=epochs*capacity;
    unsigned char *seen=calloc(cells,sizeof(*seen));
    assert(seen);
    for(size_t epoch=0;epoch<epochs;++epoch){
        size_t previous=0;
        for(size_t frequency=0;frequency<capacity;++frequency){
            size_t index=leo_research_interval_bound_index(epoch,frequency,capacity);
            assert(index<cells);
            assert(!seen[index]);
            seen[index]=1;
            if(frequency)assert(index==previous+1);
            previous=index;
        }
        if(epoch+1<epochs){
            size_t here=leo_research_interval_bound_index(epoch,0,capacity);
            size_t next=leo_research_interval_bound_index(epoch+1,0,capacity);
            assert(next-here==capacity);
        }
    }
    for(size_t index=0;index<cells;++index)assert(seen[index]);
    free(seen);
}

int main(void)
{
    test_shape(1,1);
    test_shape(1,22);
    test_shape(10000,22);
    test_shape(13333,22);
    puts("interval bounds layout: bijection and bounds pass");
    return 0;
}
