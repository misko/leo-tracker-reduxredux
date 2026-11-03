#pragma once

// Private recorded-data experiment. Public location contracts are unchanged.
#include "location.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

namespace leo::location::streaming {
constexpr double pi = 3.14159265358979323846;
constexpr double inf = std::numeric_limits<double>::infinity();
using Vec = std::array<double, 3>;
inline double dot(const Vec& a, const Vec& b) {
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
}
inline double norm(const Vec& a) { return std::sqrt(dot(a,a)); }
struct Region { double latitude, longitude, radius; };
struct Point { double east=0, north=0, tau=0; };
struct Site { Vec position, up; double latitude, longitude; };

inline Site site_at(const Region& r, const Point& p) {
    const double lat=r.latitude*pi/180, lon=r.longitude*pi/180;
    const Vec up={std::cos(lat)*std::cos(lon),std::cos(lat)*std::sin(lon),std::sin(lat)};
    const Vec east={-std::sin(lon),std::cos(lon),0};
    const Vec north={-std::sin(lat)*std::cos(lon),-std::sin(lat)*std::sin(lon),std::cos(lat)};
    const double d=std::hypot(p.east,p.north), angle=d/6371.0;
    Vec u{};
    for(int j=0;j<3;++j)
        u[j]=std::cos(angle)*up[j]+(d ? std::sin(angle)/d : 0)*(p.east*east[j]+p.north*north[j]);
    const double latitude=std::asin(std::clamp(u[2],-1.0,1.0));
    const double longitude=std::atan2(u[1],u[0]);
    constexpr double a=6378.137, e2=0.0066943799901413165;
    const double n=a/std::sqrt(1-e2*u[2]*u[2]);
    return {{n*u[0],n*u[1],n*(1-e2)*u[2]},u,latitude*180/pi,longitude*180/pi};
}

// A regional horizon envelope for the represented Hermite curve. The ellipsoid
// support is at least its polar radius. Region normals lie in an enlarged cap.
// guard_km covers measured interpolation error; it is NOT an SGP4 error proof.
inline bool regional_visible(const leo_orbit_snapshot& s, const Region& region,
                             double guard_km=2.0, double begin=-inf, double end=inf) {
    const Vec up=site_at(region,{}).up;
    const double cap=2*std::sin(region.radius/6330.0/2);
    for(uint32_t k=0;k+1<s.knot_count;++k) {
        const double t=s.knot_start_s+k*s.knot_step_s;
        if(t+s.knot_step_s<begin || t>end) continue;
        const auto& a=s.states[k]; const auto& b=s.states[k+1];
        for(int control=0;control<4;++control) {
            Vec v{};
            for(int j=0;j<3;++j) {
                if(control==0) v[j]=a.position_km[j];
                if(control==1) v[j]=a.position_km[j]+s.knot_step_s*a.velocity_km_s[j]/3;
                if(control==2) v[j]=b.position_km[j]-s.knot_step_s*b.velocity_km_s[j]/3;
                if(control==3) v[j]=b.position_km[j];
            }
            if(dot(v,up)+norm(v)*cap+guard_km>=6356.752314245) return true;
        }
    }
    return false;
}

struct Track {
    std::vector<double> times, measured, nodes, values;
    std::vector<unsigned char> training;
};
struct Fit { double cost=inf, offset=0, train_rms=inf, validation_rms=inf; };

// Private direct Hermite evaluation avoids revalidating a known-owned snapshot
// on every scalar query. This has the same polynomial as the checked public API.
inline bool state_at(const leo_orbit_snapshot& s, double time, leo_orbit_state& out) {
    const double coordinate=(time-s.knot_start_s)/s.knot_step_s;
    if(!std::isfinite(coordinate) || coordinate<0 || coordinate>s.knot_count-1) return false;
    const uint32_t k=std::min(static_cast<uint32_t>(coordinate),s.knot_count-2);
    const double u=coordinate-k, u2=u*u, u3=u2*u, h=s.knot_step_s;
    const auto& a=s.states[k];const auto& b=s.states[k+1];
    for(int j=0;j<3;++j) {
        out.position_km[j]=(2*u3-3*u2+1)*a.position_km[j]+(u3-2*u2+u)*h*a.velocity_km_s[j]
                          +(-2*u3+3*u2)*b.position_km[j]+(u3-u2)*h*b.velocity_km_s[j];
        out.velocity_km_s[j]=((6*u2-6*u)*a.position_km[j]+(-6*u2+6*u)*b.position_km[j])/h
                            +(3*u2-4*u+1)*a.velocity_km_s[j]+(3*u2-2*u)*b.velocity_km_s[j];
    }
    return true;
}
inline bool doppler(const leo_orbit_snapshot& s, double t, const Site& site,
                    double scale, double& value) {
    leo_orbit_state state{};
    if(!state_at(s,t,state)) return false;
    Vec q{},v{};
    for(int j=0;j<3;++j) { q[j]=state.position_km[j]-site.position[j];v[j]=state.velocity_km_s[j]; }
    if(dot(q,site.up)<0) return false;
    value=-scale*dot(q,v)/norm(q);
    return std::isfinite(value);
}
inline double evaluate(const leo_orbit_snapshot& s, const Track& tr, const Region& region,
                       const Point& p, double scale, bool endpoints,
                       std::vector<double>* residual=nullptr) {
    const Site site=site_at(region,p);
    const size_t n=endpoints ? 3 : tr.nodes.size();
    double mean=0, square=0;
    if(residual) residual->resize(n);
    for(size_t i=0;i<n;++i) {
        const size_t j=endpoints ? i*(tr.nodes.size()-1)/2 : i;
        double model;
        if(!doppler(s,tr.nodes[j]+p.tau,site,scale,model)) return inf;
        const double d=tr.values[j]-model;
        // Online centered variance avoids cancellation against large CFO offsets.
        const double delta=d-mean;mean+=delta/(i+1);square+=delta*(d-mean);
        if(residual) (*residual)[i]=d;
    }
    if(residual) for(double& d:*residual) d-=mean;
    return std::max(0.0,square/n);
}
inline Fit raw_fit(const leo_orbit_snapshot& s, const Track& tr, const Region& region,
                   const Point& p, double scale) {
    const Site site=site_at(region,p);
    std::vector<double> residual(tr.times.size());
    double offset=0;size_t training=0;
    for(size_t i=0;i<tr.times.size();++i) {
        double model;
        if(!doppler(s,tr.times[i]+p.tau,site,scale,model)) return {};
        residual[i]=tr.measured[i]-model;
        if(tr.training[i]) {offset+=residual[i];++training;}
    }
    offset/=training;
    double a=0,b=0;
    for(size_t i=0;i<residual.size();++i) {
        const double e=residual[i]-offset;
        (tr.training[i] ? a : b)+=e*e;
    }
    return {a/training,offset,std::sqrt(a/training),std::sqrt(b/(residual.size()-training))};
}

inline bool solve3(double a[3][3], double b[3], double out[3]) {
    for(int k=0;k<3;++k) {
        int pivot=k;for(int i=k+1;i<3;++i)if(std::abs(a[i][k])>std::abs(a[pivot][k]))pivot=i;
        if(std::abs(a[pivot][k])<1e-18) return false;
        for(int j=k;j<3;++j)std::swap(a[k][j],a[pivot][j]);std::swap(b[k],b[pivot]);
        for(int i=k+1;i<3;++i) {
            const double f=a[i][k]/a[k][k];
            for(int j=k;j<3;++j)a[i][j]-=f*a[k][j];b[i]-=f*b[k];
        }
    }
    for(int i=2;i>=0;--i) {
        out[i]=b[i];for(int j=i+1;j<3;++j)out[i]-=a[i][j]*out[j];out[i]/=a[i][i];
    }
    return true;
}
inline Point bounded(Point p, const Region& r, double tau_bound) {
    const double d=std::hypot(p.east,p.north);
    if(d>r.radius) {p.east*=r.radius/d;p.north*=r.radius/d;}
    p.tau=std::clamp(p.tau,-tau_bound,tau_bound);return p;
}
inline Point refine(const leo_orbit_snapshot& s, const Track& tr, const Region& region,
                    Point p, double scale, double tau_bound) {
    double lambda=0.01;
    std::vector<double> residual,changed;
    double cost=evaluate(s,tr,region,p,scale,false,&residual);
    if(!std::isfinite(cost))return p;
    for(int iteration=0;iteration<18;++iteration) {
        std::array<std::vector<double>,3> j;
        bool valid=true;
        for(int column=0;column<3;++column) {
            const double h=column==2 ? .05 : .25;
            Point q=p;
            if(column==0)q.east+=h;if(column==1)q.north+=h;if(column==2)q.tau+=h;
            if(!std::isfinite(evaluate(s,tr,region,q,scale,false,&changed))) {valid=false;break;}
            j[column].resize(residual.size());
            for(size_t i=0;i<residual.size();++i)j[column][i]=(residual[i]-changed[i])/h;
        }
        if(!valid)break;
        double a[3][3]{},b[3]{},step[3]{};
        for(int k=0;k<3;++k) {
            for(size_t i=0;i<residual.size();++i)b[k]+=j[k][i]*residual[i];
            for(int l=0;l<3;++l)for(size_t i=0;i<residual.size();++i)a[k][l]+=j[k][i]*j[l][i];
            a[k][k]+=lambda*std::max(1.0,a[k][k]);
        }
        if(!solve3(a,b,step))break;
        const double factor=std::min({1.0,50.0/std::max(50.0,std::hypot(step[0],step[1])),
                                     20.0/std::max(20.0,std::abs(step[2]))});
        Point q=bounded({p.east+factor*step[0],p.north+factor*step[1],p.tau+factor*step[2]},region,tau_bound);
        const double next=evaluate(s,tr,region,q,scale,false,&changed);
        if(next<cost) {
            const double improvement=cost-next;p=q;cost=next;residual.swap(changed);lambda=std::max(1e-8,lambda/3);
            if(improvement<1e-7)break;
        } else lambda=std::min(1e10,lambda*10);
    }
    return p;
}
} // namespace leo::location::streaming
