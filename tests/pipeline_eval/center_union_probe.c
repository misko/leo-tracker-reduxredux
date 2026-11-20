#include <stdint.h>
#include <string.h>
#include "center_union.h"

int main(void)
{
    unsigned char supported[10]={0,1,1,1,0,0,0,1,1,1};
    const double coarse[10]={0,1,2,4,9,3,1,2,3,4};
    if (leo_union_add(supported,10,2)!=0 || leo_union_add(supported,10,-1)!=0)
        return 1;
    if (leo_union_add(supported,10,4)!=2 || supported[3]!=1 || supported[4]!=2 ||
        supported[5]!=2 || supported[6]!=0)
        return 2;
    /* The stronger newly covered neighbor leaves the original stock peak
     * nominated. The new regional peak goes to the same final top-K. */
    if (!leo_union_local_peak(coarse,supported,10,3) ||
        !leo_union_local_peak(coarse,supported,10,4) ||
        leo_union_local_peak(coarse,supported,10,5))
        return 3;
    memset(supported,0,sizeof(supported));
    if (leo_union_add(supported,10,9)!=2 || supported[0]!=0 || supported[9]!=2 ||
        leo_union_add(supported,10,0)!=2 || supported[0]!=2 || supported[1]!=2)
        return 4;
    return 0;
}
