// Report-only, double-precision implementation of the deployed interpolator.
// No fast-math; the Python scorer remains the oracle.
#include <cmath>
#include <algorithm>
extern "C" int predict(int n, int k, int t, double node0, double step,
 const double* times, const double* rf, const double* shifts,
 const double* pos, const double* vel, const double* site, const double* up,
 const double* jac, int derivatives, double* prediction, unsigned char* visible,
 double* spatial, double* timing) {
 for(int i=0;i<n;i++) for(int j=0;j<k;j++) {
  double query=times[i]+shifts[j];
  if(query<node0 || query>node0+(t-1)*step) return 1;
  double frac=(query-node0)/step;
  int lo=std::min(int(std::floor(frac)),t-2); double w=frac-lo;
  long index=(long(j)*t+lo)*3, out=long(i)*k+j;
  double delta[3],v[3],pr[3],acc[3],d[3];
  double dist2=0;
  for(int a=0;a<3;a++) {
   double pd=pos[index+3+a]-pos[index+a], vd=vel[index+3+a]-vel[index+a];
   delta[a]=pos[index+a]+w*pd-site[a]; v[a]=vel[index+a]+w*vd;
   pr[a]=pd/step; acc[a]=vd/step; dist2+=delta[a]*delta[a];
  }
  double dist=std::sqrt(dist2); if(dist<=0) return 2;
  double radial=0,elevation=0,dr=0;
  for(int a=0;a<3;a++) { d[a]=delta[a]/dist; radial+=d[a]*v[a]; elevation+=d[a]*up[a]; dr+=d[a]*pr[a]; }
  double factor=rf[i]/299792.458;
  prediction[out]=-factor*radial; visible[out]=elevation>=0;
  if(derivatives) {
   for(int axis=0;axis<2;axis++) {
    double value=0;
    for(int a=0;a<3;a++) value+=(factor*(v[a]-radial*d[a])/dist)*jac[axis*3+a];
    spatial[out*2+axis]=value;
   }
   double rate=0;
   for(int a=0;a<3;a++) rate+=((pr[a]-d[a]*dr)/dist)*v[a]+d[a]*acc[a];
   timing[out]=-factor*rate;
  }
 }
 return 0;
}
