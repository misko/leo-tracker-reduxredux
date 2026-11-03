// Research-only configuration sweep. Production tracking/configuration unchanged.
#define main frozen_cli_main
#include "../tracking_cli.cpp"
#undef main
#include <chrono>

int main(int argc, char** argv) {
    try {
        if (argc != 5 && argc != 8 && argc != 9) throw std::invalid_argument(
            "usage: grid_trial INPUT.tsv SLOPE_BINS PEAKS INTERCEPT_BINS [MIN_SUPPORT MIN_SPAN MAX_TRACKS [MAX_GAP]]");
        leo::adaptive::tracking::Config config;
        const int slopes = parse_integer<int>(argv[2], "slope bins");
        const int peaks = parse_integer<int>(argv[3], "peaks");
        const int intercepts = parse_integer<int>(argv[4], "intercept bins");
        if (slopes < 2 || slopes > 3601 || peaks < 1 || peaks > 256 ||
            intercepts < 1 || intercepts > 2048)
            throw std::invalid_argument("research grid outside bounded range");
        config.slope_bins = slopes;
        config.peak_candidates = peaks;
        config.intercept_bins = intercepts;
        if (argc >= 8) {
            const int support = parse_integer<int>(argv[5], "minimum support");
            const double span = parse_double(argv[6], "minimum span");
            const int tracks = parse_integer<int>(argv[7], "maximum tracks");
            if (support < 6 || support > 100 || !(span >= 3 && span <= 30) ||
                tracks < 1 || tracks > 32)
                throw std::invalid_argument("research track limits outside bounded range");
            config.minimum_support = support;
            config.minimum_span_s = span;
            config.maximum_tracks_per_lane = tracks;
        }
        if (argc == 9) {
            const double gap = parse_double(argv[8], "maximum gap");
            if (!(gap >= 4 && gap <= 12)) throw std::invalid_argument("unbounded maximum gap");
            config.maximum_gap_s = gap;
        }
        std::ifstream input(argv[1]);
        std::string line;
        if (!std::getline(input, line) || line !=
            "candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\t"
            "support_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\t"
            "measured_cfo_hz\texact_score\tcontrol_score\tmargin")
            throw std::invalid_argument("unsupported input header");
        std::vector<leo::adaptive::tracking::Candidate> candidates;
        std::size_t line_number = 1;
        while (std::getline(input, line)) {
            ++line_number;
            if (!line.empty()) candidates.push_back(parse_candidate(split_tabs(line), line_number));
        }
        const auto started = std::chrono::steady_clock::now();
        const auto result = leo::adaptive::tracking::reconstruct(candidates, config);
        const double seconds = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - started).count();
        std::cerr << std::setprecision(17) << "{\"reconstruct_s\":" << seconds
                  << ",\"slope_bins\":" << slopes << ",\"peaks\":" << peaks
                  << ",\"intercept_bins\":" << intercepts
                  << ",\"minimum_support\":" << config.minimum_support
                  << ",\"minimum_span_s\":" << config.minimum_span_s
                  << ",\"maximum_tracks_per_lane\":" << config.maximum_tracks_per_lane
                  << ",\"maximum_gap_s\":" << config.maximum_gap_s << "}\n";
        std::cout << std::setprecision(17);
        std::cout << "SUMMARY\t" << result.input_candidate_count << '\t'
                  << result.used_candidate_count << '\t' << result.tracks.size() << '\n';
        std::cout << "CONFIG\t" << result.config_digest << '\n';
        for (std::size_t i = 0; i < result.tracks.size(); ++i) {
            const auto& t = result.tracks[i];
            std::cout << "TRACK\t" << i << '\t' << t.segment_id << '\t' << t.tracklet_id
                << '\t' << t.lane.receiver_id << '\t' << t.lane.channel << '\t'
                << t.lane.edge << '\t' << t.lane.actual_rf_hz << '\t' << t.start_utc_ns
                << '\t' << t.end_utc_ns << '\t' << t.reference_utc_ns << '\t'
                << t.normalized_rate_hz_per_s << '\t' << t.normalized_intercept_hz
                << '\t' << t.residual_rms_hz << '\t' << t.residual_max_hz << '\t'
                << t.weighted_support << '\t' << t.points.size() << '\n';
            for (const auto& p : t.points)
                std::cout << "POINT\t" << i << '\t' << p.candidate_id << '\t'
                    << p.source_group_id << '\t' << p.relative_alias_index << '\t'
                    << p.normalized_raw_cfo_hz << '\t' << p.normalized_dealiased_cfo_hz << '\n';
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
