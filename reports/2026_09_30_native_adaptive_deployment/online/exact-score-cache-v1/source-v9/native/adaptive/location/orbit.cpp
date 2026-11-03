#include "location.h"

#include "vendor/sgp4/SGP4.h"

#include <cmath>
#include <cstring>
#include <limits>
#include <new>
#include <utility>
#include <vector>

struct leo_orbit_context {
    uint32_t max_satellites;
    uint32_t max_knots;
    std::vector<int32_t> ids[2];
    std::vector<leo_orbit_state> states[2];
    unsigned active;
    bool has_snapshot;
    leo_orbit_snapshot snapshot;
};

namespace {
constexpr double kNanosecondsPerDay = 86400000000000.0;
constexpr double kEarthRotationRadS = 7.292115146706979e-5;

bool finite_state(const leo_orbit_state &state) {
    for (unsigned index = 0; index < 3; ++index) {
        if (!std::isfinite(state.position_km[index]) ||
            !std::isfinite(state.velocity_km_s[index])) {
            return false;
        }
    }
    return true;
}

bool valid_snapshot(const leo_orbit_snapshot *snapshot) {
    if (snapshot == nullptr || snapshot->generation == 0 ||
        snapshot->satellite_count == 0 || snapshot->knot_count < 2 ||
        snapshot->satellite_ids == nullptr || snapshot->states == nullptr ||
        !std::isfinite(snapshot->knot_start_s) ||
        !std::isfinite(snapshot->knot_step_s) || snapshot->knot_step_s <= 0.0) {
        return false;
    }
    const double end = snapshot->knot_start_s +
        snapshot->knot_step_s * static_cast<double>(snapshot->knot_count - 1);
    return std::isfinite(end);
}

bool tle_line_valid(const char *line, char number) {
    if (line == nullptr || line[0] != number || line[1] != ' ') {
        return false;
    }
    for (unsigned index = 0; index < 69; ++index) {
        const unsigned char value = static_cast<unsigned char>(line[index]);
        if (value == 0 || value < 0x20 || value > 0x7e) {
            return false;
        }
    }
    return line[69] == '\0';
}

void copy_tle_line(char destination[130], const char source[70]) {
    std::memset(destination, 0, 130);
    std::memcpy(destination, source, 69);
    /* The pinned implementation reads fields ending at column 68. Match the
     * validated prototype and do not pass the checksum as field text. */
    destination[68] = '\0';
    for (unsigned index = 2; index < 7; ++index) {
        if (destination[index] == ' ') {
            destination[index] = '0';
        }
    }
}
}  // namespace

extern "C" leo_orbit_context *leo_orbit_context_create(
    uint32_t max_satellites, uint32_t max_knots) {
    if (max_satellites == 0 || max_knots < 2 || max_satellites > 20000 ||
        max_knots > 2000) {
        return nullptr;
    }
    try {
        auto *context = new leo_orbit_context{};
        context->max_satellites = max_satellites;
        context->max_knots = max_knots;
        const size_t state_capacity =
            static_cast<size_t>(max_satellites) * max_knots;
        for (unsigned bank = 0; bank < 2; ++bank) {
            context->ids[bank].resize(max_satellites);
            context->states[bank].resize(state_capacity);
        }
        context->active = 0;
        context->has_snapshot = false;
        return context;
    } catch (...) {
        return nullptr;
    }
}

extern "C" void leo_orbit_context_destroy(leo_orbit_context *context) {
    delete context;
}

extern "C" leo_location_status leo_orbit_build_tle(
    leo_orbit_context *context,
    uint64_t generation,
    int64_t start_utc_ns,
    double knot_start_s,
    double knot_step_s,
    uint32_t knot_count,
    const leo_tle_record *records,
    uint32_t satellite_count,
    leo_orbit_snapshot *snapshot) {
    if (context == nullptr || snapshot == nullptr || records == nullptr ||
        generation == 0 || satellite_count == 0 || knot_count < 2 ||
        satellite_count > context->max_satellites || knot_count > context->max_knots ||
        !std::isfinite(knot_start_s) || !std::isfinite(knot_step_s) ||
        knot_step_s <= 0.0) {
        return LEO_LOCATION_INVALID;
    }
    const long double last_ns = static_cast<long double>(start_utc_ns) +
        (static_cast<long double>(knot_start_s) +
         static_cast<long double>(knot_step_s) * (knot_count - 1)) * 1.0e9L;
    if (last_ns < static_cast<long double>(std::numeric_limits<int64_t>::min()) ||
        last_ns > static_cast<long double>(std::numeric_limits<int64_t>::max())) {
        return LEO_LOCATION_INVALID;
    }

    try {
        std::vector<elsetrec> satellites(satellite_count);
        for (uint32_t index = 0; index < satellite_count; ++index) {
            if (records[index].satellite_id <= 0 ||
                !tle_line_valid(records[index].line1, '1') ||
                !tle_line_valid(records[index].line2, '2')) {
                return LEO_LOCATION_INVALID;
            }
            char line1[130];
            char line2[130];
            copy_tle_line(line1, records[index].line1);
            copy_tle_line(line2, records[index].line2);
            double dummy = 0.0;
            SGP4Funcs::twoline2rv(
                line1, line2, ' ', ' ', 'i', wgs72,
                dummy, dummy, dummy, satellites[index]);
            if (satellites[index].error != 0) {
                return LEO_LOCATION_ORBIT_ERROR;
            }
            satellites[index].jdsatepochF =
                std::round(satellites[index].jdsatepochF * 1.0e8) / 1.0e8;
        }

        std::vector<double> jd(knot_count);
        std::vector<double> fraction(knot_count);
        std::vector<double> cosine(knot_count);
        std::vector<double> sine(knot_count);
        for (uint32_t knot = 0; knot < knot_count; ++knot) {
            const long double relative_ns =
                (static_cast<long double>(knot_start_s) +
                 static_cast<long double>(knot_step_s) * knot) * 1.0e9L;
            const int64_t epoch_ns = start_utc_ns + std::llround(relative_ns);
            int64_t day = epoch_ns / 86400000000000LL;
            int64_t within_day = epoch_ns % 86400000000000LL;
            if (within_day < 0) {
                --day;
                within_day += 86400000000000LL;
            }
            jd[knot] = 2440587.5 + static_cast<double>(day);
            fraction[knot] = static_cast<double>(within_day) / kNanosecondsPerDay;
            const double centuries =
                (jd[knot] - 2451545.0 + fraction[knot]) / 36525.0;
            const double sidereal_seconds =
                67310.54841 + (876600.0 * 3600.0 + 8640184.812866) * centuries +
                0.093104 * centuries * centuries -
                6.2e-6 * centuries * centuries * centuries;
            double degrees = std::fmod(sidereal_seconds / 240.0, 360.0);
            if (degrees < 0.0) {
                degrees += 360.0;
            }
            const double angle = degrees * 3.14159265358979323846 / 180.0;
            cosine[knot] = std::cos(angle);
            sine[knot] = std::sin(angle);
        }

        const unsigned staging = context->has_snapshot ? 1u - context->active : context->active;
        for (uint32_t satellite = 0; satellite < satellite_count; ++satellite) {
            context->ids[staging][satellite] = records[satellite].satellite_id;
            for (uint32_t knot = 0; knot < knot_count; ++knot) {
                const double minutes =
                    (jd[knot] - satellites[satellite].jdsatepoch) * 1440.0 +
                    (fraction[knot] - satellites[satellite].jdsatepochF) * 1440.0;
                double position[3];
                double velocity[3];
                if (!SGP4Funcs::sgp4(satellites[satellite], minutes, position, velocity) ||
                    satellites[satellite].error != 0) {
                    return LEO_LOCATION_ORBIT_ERROR;
                }
                leo_orbit_state &output = context->states[staging][
                    static_cast<size_t>(satellite) * knot_count + knot];
                output.position_km[0] = cosine[knot] * position[0] + sine[knot] * position[1];
                output.position_km[1] = -sine[knot] * position[0] + cosine[knot] * position[1];
                output.position_km[2] = position[2];
                output.velocity_km_s[0] = cosine[knot] * velocity[0] +
                    sine[knot] * velocity[1] + kEarthRotationRadS * output.position_km[1];
                output.velocity_km_s[1] = -sine[knot] * velocity[0] +
                    cosine[knot] * velocity[1] - kEarthRotationRadS * output.position_km[0];
                output.velocity_km_s[2] = velocity[2];
                if (!finite_state(output)) {
                    return LEO_LOCATION_ORBIT_ERROR;
                }
            }
        }
        context->active = staging;
        context->has_snapshot = true;
        context->snapshot = leo_orbit_snapshot{
            generation,
            start_utc_ns,
            knot_start_s,
            knot_step_s,
            satellite_count,
            knot_count,
            context->ids[staging].data(),
            context->states[staging].data(),
        };
        *snapshot = context->snapshot;
        return LEO_LOCATION_OK;
    } catch (...) {
        return LEO_LOCATION_CAPACITY;
    }
}

extern "C" leo_location_status leo_orbit_interpolate(
    const leo_orbit_snapshot *snapshot,
    uint32_t satellite_index,
    double relative_time_s,
    leo_orbit_state *state) {
    if (!valid_snapshot(snapshot) || state == nullptr ||
        satellite_index >= snapshot->satellite_count || !std::isfinite(relative_time_s)) {
        return LEO_LOCATION_INVALID;
    }
    const double coordinate =
        (relative_time_s - snapshot->knot_start_s) / snapshot->knot_step_s;
    if (coordinate < 0.0 || coordinate > static_cast<double>(snapshot->knot_count - 1)) {
        return LEO_LOCATION_INVALID;
    }
    uint32_t index = static_cast<uint32_t>(std::floor(coordinate));
    if (index >= snapshot->knot_count - 1) {
        index = snapshot->knot_count - 2;
    }
    const double u = coordinate - index;
    const double u2 = u * u;
    const double u3 = u2 * u;
    const double step = snapshot->knot_step_s;
    const leo_orbit_state &a = snapshot->states[
        static_cast<size_t>(satellite_index) * snapshot->knot_count + index];
    const leo_orbit_state &b = snapshot->states[
        static_cast<size_t>(satellite_index) * snapshot->knot_count + index + 1];
    for (unsigned component = 0; component < 3; ++component) {
        state->position_km[component] =
            (2.0 * u3 - 3.0 * u2 + 1.0) * a.position_km[component] +
            (u3 - 2.0 * u2 + u) * step * a.velocity_km_s[component] +
            (-2.0 * u3 + 3.0 * u2) * b.position_km[component] +
            (u3 - u2) * step * b.velocity_km_s[component];
        state->velocity_km_s[component] =
            ((6.0 * u2 - 6.0 * u) * a.position_km[component] +
             (-6.0 * u2 + 6.0 * u) * b.position_km[component]) / step +
            (3.0 * u2 - 4.0 * u + 1.0) * a.velocity_km_s[component] +
            (3.0 * u2 - 2.0 * u) * b.velocity_km_s[component];
    }
    return finite_state(*state) ? LEO_LOCATION_OK : LEO_LOCATION_ORBIT_ERROR;
}
