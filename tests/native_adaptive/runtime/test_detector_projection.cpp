#include "detector_projection.hpp"
#include <cassert>
#include <iostream>
#include <memory>

int main(){
    using namespace leo::adaptive;
    ProjectionSource source{};
    source.input_digest="sha256:"+std::string(64,'a');source.analysis_digest="sha256:"+std::string(64,'b');
    source.generation=1;source.anchor_counter=source.window_counter=100;
    source.anchor_utc_ns=1000000000;source.rate=2500000;source.channel=1;
    source.actual_rf_hz=11200000000.;source.continuity_qualified=true;
    auto result=std::make_unique<leo_native_glrt_result>();
    result->row_count=2;result->rows[0].receiver_id=0;result->rows[1].receiver_id=1;
    result->rows[0].candidate_count=2;
    auto& passing=result->rows[0].candidates[0];
    passing.epoch=722;passing.tracking_cfo_hz=-100;passing.exact_score=.4;
    passing.control_score=.1;passing.margin=.3;passing.glrt_complete=1;
    result->rows[0].candidates[1]=passing;result->rows[0].candidates[1].exact_score=.11;
    result->rows[0].candidates[1].margin=.01;
    auto actual=project_integer_detector_result(source,*result);assert(actual.size()==1);
    Observation expected;assert(project(source,{0,722,0,-100,.4,.1,.3,true},expected));
    assert(actual[0].observation.candidate_id==expected.candidate_id);
    assert(actual[0].observation.support_center_utc_ns==expected.support_center_utc_ns);
    assert(actual[0].candidate_rank==0);
    result->rows[1].candidate_count=1;
    result->rows[1].candidates[0]=passing;
    result->rows[1].candidates[0].tracking_cfo_hz=-200;
    const auto dual=project_integer_detector_result(source,*result);
    assert(dual.size()==2 && dual[0].observation.receiver==0 && dual[1].observation.receiver==1);
    assert(dual[0].observation.candidate_id!=dual[1].observation.candidate_id);
    assert(dual[0].observation.source_group_id!=dual[1].observation.source_group_id);
    assert(dual[0].observation.support_center_utc_ns==dual[1].observation.support_center_utc_ns);
    assert(dual[0].observation.moment2==dual[1].observation.moment2);
    assert(dual[0].observation.measured_cfo_hz==-100 && dual[1].observation.measured_cfo_hz==-200);
    std::swap(result->rows[0],result->rows[1]);
    assert(project_integer_detector_result(source,*result)[0].observation.candidate_id==expected.candidate_id);
    auto rejected=[&](){try{project_integer_detector_result(source,*result);}catch(const std::invalid_argument&){return true;}return false;};
    result->rows[0].receiver_id=0;assert(rejected());result->rows[0].receiver_id=1;
    result->rows[1].candidates[0].glrt_complete=0;assert(rejected());result->rows[1].candidates[0].glrt_complete=1;
    result->rows[0].probe_index=1;assert(rejected());result->rows[0].probe_index=0;
    result->row_count=1;assert(rejected());
    std::cout<<"direct detector projection tests passed\n";
}
