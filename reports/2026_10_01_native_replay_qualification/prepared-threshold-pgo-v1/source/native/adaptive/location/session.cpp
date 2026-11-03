#include "session.hpp"
#include "session_internal.hpp"
#include <chrono>
#include <memory>
#include <new>

namespace leo::adaptive::location {
leo_location_status search_location(LocationInputView input,const SearchOptions& options,
    SearchOutput& output,ProgressCallback progress,void* user) {
    if(!input.orbit || !input.tracks || !input.track_count || input.track_count>128 ||
       (options.workers!=1 && options.workers!=2) ||
       !std::isfinite(options.latitude_deg) || std::abs(options.latitude_deg)>90 ||
       !std::isfinite(options.longitude_deg) || std::abs(options.longitude_deg)>180 ||
       !std::isfinite(options.radius_km) || options.radius_km<=0 || options.radius_km>500)
        return LEO_LOCATION_INVALID;
    const auto& orbit=*input.orbit;
    if(!orbit.generation || !orbit.states || !orbit.satellite_ids || !orbit.satellite_count ||
       orbit.satellite_count>20000 || orbit.knot_count<2 || orbit.knot_count>2000 ||
       !std::isfinite(orbit.knot_start_s) || !std::isfinite(orbit.knot_step_s) || orbit.knot_step_s<=0)
        return LEO_LOCATION_INVALID;
    try {
        detail::BorrowedInput fixture;
        fixture.snapshot=orbit;
        fixture.tracks.assign(input.tracks,input.tracks+input.track_count);
        for(const auto& track:fixture.tracks) {
            if(track.observation_count<6 || track.observation_count>100000 || !track.weight_s ||
               !track.times_s || !track.measured_hz || !track.training_mask)return LEO_LOCATION_INVALID;
            fixture.maximum_observations=std::max(fixture.maximum_observations,track.observation_count);
        }
        detail::ScoreEngine scorer(fixture,options.workers);
#ifdef LEO_RESEARCH_CAPPED_SEARCH
        scorer.objective_only=true;
#endif
        std::unique_ptr<leo_search_context,decltype(&leo_search_context_destroy)> search(
            leo_search_context_create(400),leo_search_context_destroy);
        if(!scorer.valid() || !search)return LEO_LOCATION_CAPACITY;
        SearchOutput result;
        result.policy=leo_search_default_policy(options.radius_km);
        constexpr uint64_t generation=1;
        auto status=leo_search_begin(search.get(),generation,&result.policy);
        if(status!=LEO_LOCATION_OK)return status;
        std::vector<leo_track_score> tracks(fixture.tracks.size());
        result.evaluations.reserve(result.policy.budget_points);
        for(;;) {
            leo_search_point points[128];uint32_t count=0;
            status=leo_search_next(search.get(),generation,points,128,&count);
            if(status==LEO_LOCATION_DONE)break;
            if(status!=LEO_LOCATION_OK)return status;
            std::vector<leo_search_evaluation> batch(count);
            for(uint32_t i=0;i<count;++i) {
                const auto started=std::chrono::steady_clock::now();
                const auto site=detail::make_site(options.latitude_deg,options.longitude_deg,
                                                  points[i].east_km,points[i].north_km);
                leo_point_score point{};
                if(!detail::score_site(&scorer,fixture,site,&tracks,&point))return LEO_LOCATION_STATE;
                batch[i]={points[i].east_km,points[i].north_km,point.weighted_mse_hz2};
                result.evaluations.push_back(batch[i]);
                if(progress)progress(user,{false,static_cast<unsigned>(result.evaluations.size()-1),
                    points[i].east_km,points[i].north_km,point.residual_rmse_hz,
                    std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count()});
            }
            status=leo_search_submit(search.get(),generation,batch.data(),count);
            if(status!=LEO_LOCATION_OK)return status;
        }
        status=leo_search_get_result(search.get(),generation,&result.result);
        if(status!=LEO_LOCATION_OK)return status;
        if(!result.result.has_incumbent)return LEO_LOCATION_STATE;
        if(options.full_associations) {
            const auto started=std::chrono::steady_clock::now();
#ifdef LEO_RESEARCH_CAPPED_SEARCH
            scorer.objective_only=false;
#endif
            const auto& best=result.result.incumbent;
            const auto site=detail::make_site(options.latitude_deg,options.longitude_deg,best.east_km,best.north_km);
            if(!detail::score_site(&scorer,fixture,site,&result.associations,&result.selected_score) ||
               result.selected_score.weighted_mse_hz2!=best.weighted_mse_hz2)return LEO_LOCATION_STATE;
            if(progress)progress(user,{true,0,best.east_km,best.north_km,result.selected_score.residual_rmse_hz,
                std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count()});
        }
        output=std::move(result);
        return LEO_LOCATION_OK;
    } catch(const std::bad_alloc&) {return LEO_LOCATION_CAPACITY;}
      catch(...) {return LEO_LOCATION_STATE;}
}
}
