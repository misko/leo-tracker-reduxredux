/* Two bounded numerical kernels for the timing-first pilot receiver. */
#include <math.h>
#include <stddef.h>

enum { samples = 200000, period = 13333, frames = 14, pilot = 2816, block = 352 };
static const double tau = 6.283185307179586476925286766559;

int delay_decimate(const float *x, const float *coeff, int taps, int stride, float *out) {
    if (!x || !coeff || !out || stride < 1 || stride > 4 || taps < 1 || !(taps & 1))
        return -1;
    int half = taps / 2;
    for (int j = 0; j < samples / stride; ++j) {
        int mid = j * stride;
        float re = x[2 * mid] * coeff[half];
        float im = x[2 * mid + 1] * coeff[half];
        if (mid >= half && mid + half < samples) {
            #pragma omp simd reduction(+:re,im)
            for (int d = 1; d <= half; ++d) {
                re += coeff[half + d] * (x[2 * (mid - d)] + x[2 * (mid + d)]);
                im += coeff[half + d] * (x[2 * (mid - d) + 1] + x[2 * (mid + d) + 1]);
            }
        } else {
            for (int d = -half; d <= half; ++d) {
                if (d && mid+d >= 0 && mid+d < samples) {
                    re += coeff[half + d] * x[2*(mid+d)];
                    im += coeff[half + d] * x[2*(mid+d)+1];
                }
            }
        }
        out[2*j] = re;
        out[2*j+1] = im;
    }
    return 0;
}

int delay_refine(const float *x, const float *h, int epoch, double hz,
                 double lo, double hi, double *out) {
    if (!x || !h || !out || epoch < 0 || epoch >= period || !isfinite(hz) || !(hi > lo))
        return -1;
    float hr[pilot], hiq[pilot];
    double phi = -tau * hz / 1e7, dr=cos(phi), di=sin(phi), re=1., im=0., energy=0.;
    for (int j=0; j<pilot; ++j) {
        hr[j] = (float)(h[2*j]*re + h[2*j+1]*im);
        hiq[j] = (float)(h[2*j]*im - h[2*j+1]*re);
        energy += h[2*j]*h[2*j] + h[2*j+1]*h[2*j+1];
        double next = re*dr - im*di;
        im = re*di + im*dr;
        re = next;
    }
    double score[9], freqs[9];
    int best=0;
    for (int i=0; i<9; ++i) {
        int e=(epoch+i-4+period)%period;
        float zr[frames][8], zi[frames][8];
        double er[2]={0.,0.}, lr=0., li=0.;
        for (int f=0; f<frames; ++f) {
            int offset=(40000*f+1)/3 + 88 + e;
            for (int b=0; b<8; ++b) {
                float a=0.f, c=0.f, power=0.f;
                #pragma omp simd reduction(+:a,c,power)
                for (int k=0; k<block; ++k) {
                    int n=b*block+k;
                    float xr=x[2*(offset+n)], xi=x[2*(offset+n)+1];
                    a += xr*hr[n]-xi*hiq[n];
                    c += xr*hiq[n]+xi*hr[n];
                    power += xr*xr+xi*xi;
                }
                zr[f][b]=a;
                zi[f][b]=c;
                er[f%2]+=power;
                if (b>=4) {
                    lr+=a*zr[f][b-4]+c*zi[f][b-4];
                    li+=c*zr[f][b-4]-a*zi[f][b-4];
                }
            }
        }
        double delta=atan2(li,lr)*1e7/(tau*(pilot/2));
        freqs[i]=fmin(hi,fmax(lo,hz+delta));
        double wr[8],wi[8], sum[2]={0.,0.};
        for (int b=0;b<8;++b) {
            double angle=-tau*(freqs[i]-hz)*block*b/1e7;
            wr[b]=cos(angle); wi[b]=sin(angle);
        }
        for (int f=0;f<frames;++f) {
            double a=0., c=0.;
            for (int b=0;b<8;++b) {
                a+=zr[f][b]*wr[b]-zi[f][b]*wi[b];
                c+=zr[f][b]*wi[b]+zi[f][b]*wr[b];
            }
            sum[f%2]+=a*a+c*c;
        }
        score[i]=fmin(sum[0]/fmax(er[0]*energy,1e-15),sum[1]/fmax(er[1]*energy,1e-15));
        if (score[i]>score[best]) best=i;
    }
    double shift=0.;
    if (best>0 && best<8) {
        double bend=score[best-1]-2.*score[best]+score[best+1];
        if (bend<0.) shift=fmin(.5,fmax(-.5,.5*(score[best-1]-score[best+1])/bend));
    }
    int sample=(epoch+best-4+period)%period;
    out[0]=fmod(sample+shift+period,period);
    out[1]=freqs[best]; out[2]=sample; out[3]=score[best];
    return 0;
}
