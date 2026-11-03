#define LEO_PROPOSAL_LIBRARY 1
#include "proposal_core.c"
#include <assert.h>
static void exact(bank *b,int out[4],int *count){size_t z=b->fft_n;memset(b->scores[4],0,z*sizeof(float));for(int m=0;m<3;m++){if(rank_feature_flat(b->scores[m],z))continue;for(size_t k=0;k<z;k++)b->ranking[k]=(ranked){b->scores[m][k],(int)k};ranked *p=rank_radix_reference(b->ranking,b->rank_scratch,z);for(size_t r=0;r<z;r++)b->scores[4][p[r].index]+=b->scores[3][r];}*count=top4_linear(b->scores[4],z,b->n,out,b->ranking);}
int main(void){enum{Z=128,N=101};bank b={0};b.fft_n=Z;b.n=N;b.ranking=malloc(Z*sizeof(ranked));b.rank_scratch=malloc(Z*sizeof(ranked));for(int m=0;m<5;m++)b.scores[m]=calloc(Z,sizeof(float));assert(b.ranking&&b.rank_scratch);for(int r=0;r<Z;r++)b.scores[3][r]=(float)r/(Z-1);uint32_t state=1;int accepted=0;
 for(int trial=0;trial<2000;trial++){for(int m=0;m<3;m++)for(int k=0;k<Z;k++){state=1664525u*state+1013904223u;b.scores[m][k]=(float)(state&0xffffffu)/16777216.0f;}if(trial==0)for(int m=0;m<3;m++)memset(b.scores[m],0,Z*sizeof(float));if(trial==1)for(int m=0;m<3;m++)for(int k=0;k<Z;k++)b.scores[m][k]=(float)(k%7);if(trial==2)for(int m=0;m<3;m++){b.scores[m][0]=99;b.scores[m][Z-1]=98;b.scores[m][5]=97;b.scores[m][64]=96;}
  int got[4],want[4],ng=0,nw=0,c=certify_top4(&b,got,&ng);exact(&b,want,&nw);if(c){accepted++;assert(ng==nw);for(int j=0;j<ng;j++)assert(got[j]==want[j]);}}
 assert(accepted>0);printf("certified rank adversarial exact: %d/2000 accepted\n",accepted);for(int m=0;m<5;m++)free(b.scores[m]);free(b.ranking);free(b.rank_scratch);return 0;}
