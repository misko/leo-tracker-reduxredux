#include <algorithm>
#include <cmath>

// Private research ABI, double precision, no fast-math. No production linkage.
extern "C" int elevation(int n, int k, int t, double node0, double step,
    const double* times, const double* shifts, const double* pos,
    const double* site, const double* up, const double* site_jac,
    const double* up_jac, double* angles, double* spatial, double* timing) {
    const double degrees = 180.0 / std::acos(-1.0);
    for (int i=0; i<n; ++i) for (int j=0; j<k; ++j) {
        const double query = times[i] + shifts[j];
        if (query < node0 || query > node0+(t-1)*step) return 1;
        const double fraction = (query-node0)/step;
        const int lower = std::min(int(std::floor(fraction)), t-2);
        const double weight = fraction-lower;
        const long index = (long(j)*t+lower)*3, out = long(i)*k+j;
        double delta[3], rate[3], direction[3], distance2=0;
        for (int a=0; a<3; ++a) {
            const double difference = pos[index+3+a]-pos[index+a];
            delta[a] = pos[index+a]+weight*difference-site[a];
            rate[a] = difference/step;
            distance2 += delta[a]*delta[a];
        }
        const double distance = std::sqrt(distance2);
        if (distance <= 0) return 2;
        double sine=0;
        for (int a=0; a<3; ++a) {
            direction[a] = delta[a]/distance;
            sine += direction[a]*up[a];
        }
        sine = std::clamp(sine, -1.0, 1.0);
        angles[out] = degrees*std::asin(sine);
        const double factor = std::abs(sine)<1 ? degrees/std::sqrt(1-sine*sine) : 0;
        double time_derivative=0;
        for (int axis=0; axis<2; ++axis) {
            double derivative=0;
            for (int a=0; a<3; ++a) {
                const double tangent = up[a]-sine*direction[a];
                derivative += -tangent*site_jac[axis*3+a]/distance
                              +direction[a]*up_jac[axis*3+a];
            }
            spatial[out*2+axis] = derivative*factor;
        }
        for (int a=0; a<3; ++a)
            time_derivative += (up[a]-sine*direction[a])*rate[a]/distance;
        timing[out] = time_derivative*factor;
    }
    return 0;
}
