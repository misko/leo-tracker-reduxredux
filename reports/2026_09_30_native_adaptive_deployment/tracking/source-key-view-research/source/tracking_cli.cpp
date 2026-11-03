#include "tracking.hpp"
#ifdef LEO_TRACKING_EXECUTION_CLI
#include "../runtime/runtime.hpp"
#endif

#include <cerrno>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::vector<std::string> split_tabs(const std::string& line) {
    std::vector<std::string> fields;
    std::size_t start = 0;
    while (true) {
        const std::size_t end = line.find('\t', start);
        fields.push_back(line.substr(start, end - start));
        if (end == std::string::npos) return fields;
        start = end + 1;
    }
}

template <typename Integer>
Integer parse_integer(const std::string& text, const char* name) {
    errno = 0;
    char* end = nullptr;
    const long long parsed = std::strtoll(text.c_str(), &end, 10);
    if (errno != 0 || end != text.c_str() + text.size() ||
        parsed < static_cast<long long>(std::numeric_limits<Integer>::min()) ||
        parsed > static_cast<long long>(std::numeric_limits<Integer>::max())) {
        throw std::runtime_error(std::string("invalid ") + name);
    }
    return static_cast<Integer>(parsed);
}

double parse_double(const std::string& text, const char* name) {
    char* end = nullptr;
    const double value = std::strtod(text.c_str(), &end);
    if (end != text.c_str() + text.size()) {
        throw std::runtime_error(std::string("invalid ") + name);
    }
    return value;
}

leo::adaptive::tracking::Candidate parse_candidate(
    const std::vector<std::string>& fields,
    std::size_t line_number) {
    if (fields.size() != 13) {
        throw std::runtime_error(
            "line " + std::to_string(line_number) + " must contain 13 tab-separated fields");
    }
    using leo::adaptive::tracking::Candidate;
    return Candidate{
        fields[0],
        fields[1],
        parse_integer<int>(fields[2], "receiver_id"),
        parse_integer<int>(fields[3], "channel"),
        fields[4],
        parse_double(fields[5], "actual_rf_hz"),
        parse_integer<std::int64_t>(fields[6], "support_start_utc_ns"),
        parse_integer<std::int64_t>(fields[7], "support_center_utc_ns"),
        parse_integer<std::int64_t>(fields[8], "support_end_utc_ns"),
        parse_double(fields[9], "measured_cfo_hz"),
        parse_double(fields[10], "exact_score"),
        parse_double(fields[11], "control_score"),
        parse_double(fields[12], "margin"),
    };
}

}  // namespace

#ifdef LEO_TRACKING_EXECUTION_CLI
namespace {
void dispatch_lanes(void* opaque,std::size_t count,void* task_context,
                    void (*task)(void*,std::size_t)) {
    auto& executor=*static_cast<leo::adaptive::Executor*>(opaque);
    struct Task { void* context;void (*run)(void*,std::size_t);std::size_t index; };
    std::vector<Task> tasks;tasks.reserve(count);
    for(std::size_t index=0;index<count;++index) tasks.push_back({task_context,task,index});
    try {
        for(auto& item:tasks) {
            const leo::adaptive::Job job{item.index,[](void* argument,std::size_t) {
                auto& work=*static_cast<Task*>(argument);work.run(work.context,work.index);
            },&item};
            while(!executor.submit(job)) {
                executor.drain();executor.rethrow_first_failure();
            }
        }
        executor.drain();executor.rethrow_first_failure();
    } catch (...) {
        executor.drain(); // Borrowed task arguments outlive every accepted job.
        throw;
    }
}
}
#endif

int main(int argc, char** argv) {
#ifdef LEO_TRACKING_EXECUTION_CLI
    if (argc!=2 && (argc!=4 || std::string(argv[2])!="--workers")) {
        std::cerr << "usage: " << argv[0] << " CANDIDATES.tsv [--workers 1..4]\n";
        return 2;
    }
#else
    if (argc != 2) {
        std::cerr << "usage: " << argv[0] << " CANDIDATES.tsv\n";
        return 2;
    }
#endif
    try {
#ifdef LEO_TRACKING_EXECUTION_CLI
        const int workers=argc==4?parse_integer<int>(argv[3],"workers"):1;
        if(workers<1 || workers>4) throw std::invalid_argument("workers must be 1..4");
#endif
        std::ifstream input(argv[1]);
        if (!input) throw std::runtime_error("cannot open candidate input");
        std::string line;
        if (!std::getline(input, line) || line !=
            "candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\t"
            "support_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\t"
            "measured_cfo_hz\texact_score\tcontrol_score\tmargin") {
            throw std::runtime_error("candidate input has an unsupported header");
        }
        std::vector<leo::adaptive::tracking::Candidate> candidates;
        std::size_t line_number = 1;
        while (std::getline(input, line)) {
            ++line_number;
            if (!line.empty()) candidates.push_back(parse_candidate(split_tabs(line), line_number));
        }
        leo::adaptive::tracking::Result result;
#ifdef LEO_TRACKING_EXECUTION_CLI
        if(workers>1) {
            leo::adaptive::Executor executor(static_cast<std::size_t>(workers),16);
            result=leo::adaptive::tracking::reconstruct(candidates,{},
                {&executor,dispatch_lanes});
        } else
#endif
        result=leo::adaptive::tracking::reconstruct(candidates);
        std::cout << std::setprecision(17);
        std::cout << "SUMMARY\t" << result.input_candidate_count << '\t'
                  << result.used_candidate_count << '\t' << result.tracks.size() << '\n';
        std::cout << "CONFIG\t" << result.config_digest << '\n';
        for (std::size_t track_index = 0; track_index < result.tracks.size(); ++track_index) {
            const auto& track = result.tracks[track_index];
            std::cout << "TRACK\t" << track_index << '\t' << track.segment_id << '\t'
                      << track.tracklet_id << '\t'
                      << track.lane.receiver_id << '\t' << track.lane.channel << '\t'
                      << track.lane.edge << '\t' << track.lane.actual_rf_hz << '\t'
                      << track.start_utc_ns << '\t' << track.end_utc_ns << '\t'
                      << track.reference_utc_ns << '\t' << track.normalized_rate_hz_per_s << '\t'
                      << track.normalized_intercept_hz << '\t' << track.residual_rms_hz << '\t'
                      << track.residual_max_hz << '\t' << track.weighted_support << '\t'
                      << track.points.size() << '\n';
            for (const auto& point : track.points) {
                std::cout << "POINT\t" << track_index << '\t' << point.candidate_id << '\t'
                          << point.source_group_id << '\t' << point.relative_alias_index << '\t'
                          << point.normalized_raw_cfo_hz << '\t'
                          << point.normalized_dealiased_cfo_hz << '\n';
            }
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "tracking: " << error.what() << '\n';
        return 1;
    }
}
