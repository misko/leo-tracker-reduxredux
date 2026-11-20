#include "private_namespace.h"
#include "proposal_core.h"
#include <stdio.h>
#include <stdlib.h>

static int load(const char *name,void *items,size_t bytes)
{
    FILE *file=fopen(name,"rb");
    if(!file)return -1;
    int ok=fread(items,1,bytes,file)==bytes&&fgetc(file)==EOF;
    fclose(file);
    return ok?0:-1;
}

int main(int argc,char **argv)
{
    if(argc!=3)return 2;
    const size_t frame=13333,count=200000;
    double (*reference)[2]=malloc(frame*sizeof(*reference));
    int16_t *iq=malloc(count*4*sizeof(*iq));
    if(!reference||!iq||load(argv[1],reference,frame*sizeof(*reference))||
        load(argv[2],iq,count*4*sizeof(*iq)))return 3;
    leo_proposal_workspace *workspace=leo_proposal_create(reference,frame,10000000.0);
    if(!workspace)return 4;
    for(int rx=0;rx<2;++rx){
        int top4[4],top16[16],n4,n16;
        if(leo_proposal_top4(workspace,iq,0,rx,top4,&n4,NULL)||
            leo_proposal_ranked(workspace,iq,0,rx,top16,16,&n16,NULL))return 5;
        if(n4<0||n4>4||n16<n4||n16>16)return 6;
        for(int i=0;i<n4;++i)if(top4[i]!=top16[i])return 7;
        for(int i=0;i<n16;++i)printf("%s%d",i?" ":"",top16[i]);
        putchar('\n');
    }
    leo_proposal_destroy(workspace);
    free(iq);free(reference);
    return 0;
}
