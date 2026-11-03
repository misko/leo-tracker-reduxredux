#include "projection.hpp"
#include "server_compat.hpp"

#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

int main(int argc, char**) {
    if (argc != 1) return 2;
    std::string line;
    std::size_t line_number = 0;
    try {
        leo::adaptive::server_compat::SupportDeriver deriver(
            leo::adaptive::server_compat::authority_binding());
        const auto port = leo::adaptive::server_compat::derivation_port(deriver);
        while (std::getline(std::cin, line)) {
            ++line_number;
            if (line.size() > 4096) throw std::invalid_argument("oversized record");
            std::istringstream input(line);
            leo::adaptive::ProjectionSource source{};
            leo::adaptive::FractionalCandidate candidate{};
            unsigned upper = 0;
            unsigned complete = 0;
            unsigned qualified = 0;
            std::string extra;
            if (!(input >> source.rate >> source.anchor_counter >> source.anchor_utc_ns >>
                  source.generation >> source.visit >> source.window_counter >>
                  source.probe_index >> source.receiver >> source.channel >> upper >>
                  source.actual_rf_hz >> source.utc_bracket_width_ns >> source.input_digest >>
                  source.analysis_digest >> qualified >> candidate.rank >>
                  candidate.integer_epoch >> candidate.fractional_offset >>
                  candidate.tracking_cfo_hz >> candidate.exact_score >>
                  candidate.control_score >> candidate.margin >> complete) ||
                (input >> extra) || upper > 1 || complete > 1 || qualified > 1) {
                throw std::invalid_argument("invalid projection record");
            }
            source.upper_edge = upper != 0;
            source.continuity_qualified = qualified != 0;
            candidate.complete = complete != 0;
            leo::adaptive::Observation observation;
            leo::adaptive::SupportDerivation support;
            const auto status = leo::adaptive::project(
                source, candidate, port, observation, support);
            if (status == leo::adaptive::SupportProjectionStatus::nonpassing) {
                std::cout << "unavailable\n";
                continue;
            }
            if (status != leo::adaptive::SupportProjectionStatus::emitted) {
                throw std::runtime_error("support-profile projection failed");
            }
            std::cout << std::setprecision(17) << observation.candidate_id << '\t'
                      << observation.source_group_id << '\t'
                      << observation.support_start_utc_ns << '\t'
                      << observation.support_center_utc_ns << '\t'
                      << observation.support_end_utc_ns << '\t'
                      << observation.measured_cfo_hz << '\t'
                      << observation.standard_uncertainty_hz << '\t'
                      << support.factorial_moment_lexemes[2] << '\t'
                      << support.factorial_moment_lexemes[3] << '\n';
        }
        if (!std::cin.eof()) throw std::runtime_error("input read failed");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "server-compatible projection record " << line_number << ": "
                  << error.what() << '\n';
        return 2;
    }
}
