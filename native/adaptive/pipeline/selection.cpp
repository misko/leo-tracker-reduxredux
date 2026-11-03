#include "selection.hpp"
#include "sha256.hpp"
#include <algorithm>
#include <cmath>
#include <numeric>
#include <set>
#include <stdexcept>
#include <unordered_map>

namespace leo::adaptive::pipeline {
tracking::Result select_exclusive_candidates(const tracking::Result& input,
    const std::vector<tracking::Candidate>& observations, SelectionAudit& audit) {
    audit={};audit.input_tracks=input.tracks.size();
    std::unordered_map<std::string,const tracking::Candidate*> source;
    for(const auto& o:observations)if(!source.emplace(o.candidate_id,&o).second)
        throw std::invalid_argument("duplicate selection observation");
    std::vector<std::size_t> order(input.tracks.size());std::iota(order.begin(),order.end(),0);
    std::stable_sort(order.begin(),order.end(),[&](auto a,auto b) {
        const auto& x=input.tracks[a];const auto& y=input.tracks[b];
        const auto dx=x.end_utc_ns-x.start_utc_ns,dy=y.end_utc_ns-y.start_utc_ns;
        return dx!=dy ? dx>dy : x.points.size()>y.points.size();
    });
    tracking::Result output;output.input_candidate_count=input.input_candidate_count;
    output.config_digest="sha256:"+leo::adaptive::sha256("exclusive-candidates-longest-v1\n"+input.config_digest);
    std::set<std::string> claimed;
    for(auto index:order) {
        const auto& original=input.tracks[index];
        auto points=original.points;
        std::stable_sort(points.begin(),points.end(),[&](const auto& a,const auto& b) {
            return source.at(a.candidate_id)->support_center_utc_ns<source.at(b.candidate_id)->support_center_utc_ns;
        });
        std::vector<tracking::TrackPoint> fragment;
        auto emit=[&]() {
            if(fragment.empty())return;
            const auto& first=*source.at(fragment.front().candidate_id);
            const auto& last=*source.at(fragment.back().candidate_id);
            if(fragment.size()<8 || last.support_center_utc_ns-first.support_center_utc_ns<4000000000LL) {
                audit.insufficient_memberships_removed+=fragment.size();fragment.clear();return;
            }
            auto track=original;track.points=fragment;
            track.start_utc_ns=first.support_start_utc_ns;track.end_utc_ns=last.support_end_utc_ns;
            std::string identity="exclusive-candidates-longest-v1\n"+original.tracklet_id;
            for(const auto& p:fragment) {
                claimed.insert(p.candidate_id);identity+='\n'+p.candidate_id+':'+std::to_string(p.relative_alias_index);
                const auto* observation=source.at(p.candidate_id);
                track.start_utc_ns=std::min(track.start_utc_ns,observation->support_start_utc_ns);
                track.end_utc_ns=std::max(track.end_utc_ns,observation->support_end_utc_ns);
            }
            track.tracklet_id="sha256:"+leo::adaptive::sha256(identity);track.segment_id=track.tracklet_id;
            output.tracks.push_back(std::move(track));fragment.clear();
        };
        for(const auto& point:points) {
            if(claimed.count(point.candidate_id)) {++audit.reused_memberships_removed;continue;}
            if(!fragment.empty() && source.at(point.candidate_id)->support_center_utc_ns-
                source.at(fragment.back().candidate_id)->support_center_utc_ns>4000000000LL)emit();
            fragment.push_back(point);
        }
        emit();
    }
    output.used_candidate_count=claimed.size();audit.output_tracks=output.tracks.size();
    return output;
}
}
