#pragma once
#include "tracking.hpp"
#include <istream>

namespace leo::adaptive::pipeline {
// Research TSV port shared by the frozen tracker CLIs. Reads memberships;
// never reconstructs tracks or consults reference memberships.
tracking::Result read_track_checkpoint(
    std::istream& input, const std::vector<tracking::Candidate>& observations);
}
