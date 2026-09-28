/* Exercise cancellation, block boundaries and all supported template lengths. */
#include "full_search.c"
#include <assert.h>

static unsigned state=17;
static double sample(void)
{
    state=1664525u*state+1013904223u;
    return (double)(state>>8)/16777216.0-.5;
}

int main(void)
{
    size_t lengths[]={1,3,4,63,64,65,3333,6667,10000,13333};
    for (size_t t=0;t<sizeof(lengths)/sizeof(*lengths);++t) {
        size_t n=lengths[t];
        float *a=calloc(2*n,sizeof(float)), *b=calloc(2*n,sizeof(float));
        assert(a && b);
        for (int trial=0;trial<12;++trial) {
            double complex exact=0;
            double ea=0,eb=0;
            for (size_t k=0;k<n;++k) {
                double scale=trial%3==0 ? 1e10 : trial%3==1 ? 1e-10 : 1;
                double complex x=scale*(sample()+I*sample());
                if (trial>=6) x=(k&1 ? -1 : 1)*scale+I*sample()*scale*1e-5;
                double angle=sample()*6;
                double complex y=cos(angle)+I*sin(angle);
                a[2*k]=(float)creal(x); a[2*k+1]=(float)cimag(x);
                b[2*k]=(float)creal(y); b[2*k+1]=(float)cimag(y);
                exact+=x*y; ea+=power(x);eb+=power(y);
            }
            double complex approximate=full_blocked_dot(a,b,n);
            double difference=cabs(approximate-exact)/sqrt(ea*eb);
            assert(isfinite(difference));
            assert(difference<=128.0*FLT_EPSILON);
        }
        free(a);free(b);
    }
    return 0;
}
