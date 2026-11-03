#include <array>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <tuple>

namespace {

bool owning_less(double weight,double residual,const std::string& candidate_id,
                 double previous_weight,double previous_residual,
                 const std::string& previous_candidate_id) {
    const auto rank=std::make_tuple(-weight,std::abs(residual),candidate_id);
    const auto previous=std::make_tuple(-previous_weight,std::abs(previous_residual),
        previous_candidate_id);
    return rank<previous;
}

bool borrowed_less(double weight,double residual,const std::string& candidate_id,
                   double previous_weight,double previous_residual,
                   const std::string& previous_candidate_id) {
    const std::tuple<double,double,const std::string&> rank(
        -weight,std::abs(residual),candidate_id);
    const std::tuple<double,double,const std::string&> previous(
        -previous_weight,std::abs(previous_residual),previous_candidate_id);
    return rank<previous;
}

void require(bool condition,const char* message) {
    if (!condition) throw std::runtime_error(message);
}

} // namespace

int main() {
    constexpr double infinity=std::numeric_limits<double>::infinity();
    const std::array<double,8> weights{
        0.0,-0.0,1.0,-1.0,42.5,-42.5,infinity,-infinity};
    const std::array<double,8> residuals{
        0.0,-0.0,1.0,-1.0,19.25,-19.25,infinity,-infinity};
    const std::array<std::string,6> ids{
        std::string{},std::string{"a"},std::string{"aa"},std::string{"b"},
        std::string{"a\0b",3},std::string{"sha256:ffffffff"}};
    std::size_t comparisons=0;
    for (const double weight:weights) for (const double previous_weight:weights)
        for (const double residual:residuals)
            for (const double previous_residual:residuals)
                for (const auto& id:ids) for (const auto& previous_id:ids) {
                    require(owning_less(weight,residual,id,previous_weight,
                                previous_residual,previous_id)==
                            borrowed_less(weight,residual,id,previous_weight,
                                previous_residual,previous_id),
                        "borrowed rank ordering differs from owning tuple");
                    ++comparisons;
                }
    require(borrowed_less(1.0,2.0,"a",1.0,2.0,"b"),
        "candidate id must break an equal numeric rank");
    require(!borrowed_less(1.0,-0.0,"same",1.0,0.0,"same"),
        "signed-zero residuals must remain equivalent");
    std::cout<<"one_per_source borrowed rank comparisons passed: "
             <<comparisons<<'\n';
}
