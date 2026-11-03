#include "projection.hpp"
#include "sha256.hpp"
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
namespace leo { namespace adaptive {
namespace {
bool digest(const std::string& s) {
    return s.size()==71 && s.compare(0,7,"sha256:")==0 &&
        s.find_first_not_of("0123456789abcdef",7)==std::string::npos;
}

ProjectionInputStatus classify(const ProjectionSource& s,const FractionalCandidate& c,
                               double gate) {
    if(!s.continuity_qualified || !s.generation || !digest(s.input_digest) ||
       !digest(s.analysis_digest) || s.anchor_utc_ns<=0 || s.probe_ms!=20 ||
       !s.rate || s.rate>10000000 || s.rate%1000 ||
       s.receiver>1 || s.channel<1 || s.channel>4 ||
       !std::isfinite(s.actual_rf_hz) || s.actual_rf_hz<=0 ||
       !std::isfinite(s.utc_bracket_width_ns) || s.utc_bracket_width_ns<0 ||
       !std::isfinite(gate) || gate<0)
        throw std::invalid_argument("unqualified projection source");
    if(!c.complete) return ProjectionInputStatus::nonpassing;
    if(!std::isfinite(c.tracking_cfo_hz) || !std::isfinite(c.exact_score) ||
       !std::isfinite(c.control_score) || !std::isfinite(c.margin) ||
       c.exact_score<0 || c.control_score<0 ||
       std::abs(c.margin-(c.exact_score-c.control_score))>
           std::max(1e-12,1e-12*std::max(std::abs(c.margin),std::abs(c.exact_score-c.control_score))))
        throw std::invalid_argument("invalid fractional scores");
    if(c.margin<=0 || c.margin<gate) return ProjectionInputStatus::nonpassing;
    if(c.integer_epoch<0 ||
       c.integer_epoch>=static_cast<std::int64_t>(s.rate/50) ||
       !std::isfinite(c.fractional_offset) || std::abs(c.fractional_offset)>2.0)
        throw std::invalid_argument("invalid fractional support input");
    return ProjectionInputStatus::passing;
}

bool same_binary64(double left,double right) {
    return std::memcmp(&left,&right,sizeof(left))==0;
}

bool json_number(const std::string& text) {
    std::size_t index=0;
    if(index<text.size() && text[index]=='-') ++index;
    if(index==text.size()) return false;
    if(text[index]=='0') {
        ++index;
        if(index<text.size() && text[index]>='0' && text[index]<='9') return false;
    } else {
        if(text[index]<'1' || text[index]>'9') return false;
        while(index<text.size() && text[index]>='0' && text[index]<='9') ++index;
    }
    if(index<text.size() && text[index]=='.') {
        ++index;
        const auto begin=index;
        while(index<text.size() && text[index]>='0' && text[index]<='9') ++index;
        if(index==begin) return false;
    }
    if(index<text.size() && (text[index]=='e' || text[index]=='E')) {
        ++index;
        if(index<text.size() && (text[index]=='+' || text[index]=='-')) ++index;
        const auto begin=index;
        while(index<text.size() && text[index]>='0' && text[index]<='9') ++index;
        if(index==begin) return false;
    }
    return index==text.size();
}

bool valid_lexeme(const std::string& text,double expected) {
    if(text.empty() || text.size()>64 || !json_number(text)) return false;
    char* end=nullptr;
    errno=0;
    const double parsed=std::strtod(text.c_str(),&end);
    // Match the downstream SupportAuthority parser so rejection happens at the
    // projection boundary rather than after an event has entered the inbox.
    return errno==0 && end==text.c_str()+text.size() && std::isfinite(parsed) &&
        same_binary64(parsed,expected);
}

bool valid_derivation(const SupportDerivation& value,std::uint32_t samples) {
    const auto& support=value.numeric;
    return support.first>=0 && support.end>support.first &&
        support.end<=static_cast<std::int64_t>(samples) &&
        std::isfinite(support.center) && support.center>=support.first &&
        support.center<support.end && std::isfinite(support.moment2) &&
        support.moment2>=0 && std::isfinite(support.moment3) &&
        support.symbols>=2 && support.symbols<=1024 &&
        value.factorial_moment_lexemes[0]=="1.0" &&
        value.factorial_moment_lexemes[1]=="0.0" &&
        valid_lexeme(value.factorial_moment_lexemes[2],support.moment2) &&
        valid_lexeme(value.factorial_moment_lexemes[3],support.moment3);
}

void finish(const ProjectionSource& s,const FractionalCandidate& c,
            const Support& g,Observation& out) {
    const auto group="sha256:"+sha256("{\"capture\":\""+s.input_digest+"\",\"probe\":"+
        std::to_string(s.probe_index)+",\"rx\":"+std::to_string(s.receiver)+
        ",\"visit\":"+std::to_string(s.visit)+"}");
    const auto id="sha256:"+sha256("{\"analysis\":\""+s.analysis_digest+"\",\"group\":\""+
        group+"\",\"rank\":"+std::to_string(c.rank)+"}");
    Observation o;
    o.candidate_id=id;o.source_group_id=group;o.generation=s.generation;o.visit=s.visit;
    o.receiver=s.receiver;o.channel=s.channel;o.probe_index=s.probe_index;o.upper_edge=s.upper_edge;
    o.actual_rf_hz=s.actual_rf_hz;o.measured_cfo_hz=c.tracking_cfo_hz;
    o.exact_score=c.exact_score;o.control_score=c.control_score;o.margin=c.margin;
    o.support_start_utc_ns=support_utc_ns(s.anchor_counter,s.anchor_utc_ns,s.window_counter,g.first,s.rate);
    o.support_center_utc_ns=support_utc_ns(s.anchor_counter,s.anchor_utc_ns,s.window_counter,g.center,s.rate);
    o.support_end_utc_ns=support_utc_ns(s.anchor_counter,s.anchor_utc_ns,s.window_counter,g.end,s.rate);
    if(o.support_start_utc_ns<=0 || o.support_center_utc_ns<o.support_start_utc_ns ||
       o.support_end_utc_ns<=o.support_center_utc_ns)
        throw std::invalid_argument("invalid projected UTC support");
    o.standard_uncertainty_hz=std::hypot(400.0,15000.0*s.utc_bracket_width_ns/2e9);
    o.moment2=g.moment2;o.moment3=g.moment3;out=std::move(o);
}

}  // namespace

ProjectionInputStatus classify_projection_input(
    const ProjectionSource& source,const FractionalCandidate& candidate,double gate) {
    return classify(source,candidate,gate);
}

bool project(const ProjectionSource& s,const FractionalCandidate& c,Observation& out,double gate) {
    if(classify(s,c,gate)==ProjectionInputStatus::nonpassing) return false;
    const auto support=fractional_support(s.rate,s.rate/50,c.integer_epoch,c.fractional_offset);
    finish(s,c,support,out);
    return true;
}

bool ProjectionBatch::project(const ProjectionSource& s,const FractionalCandidate& c,
                              Observation& out,double gate) {
    if(classify(s,c,gate)==ProjectionInputStatus::nonpassing) return false;
    for(const auto& entry:entries_) {
        if(entry.valid && entry.rate==s.rate && entry.epoch==c.integer_epoch &&
           same_binary64(entry.offset,c.fractional_offset)) {
            finish(s,c,entry.support,out);
            return true;
        }
    }
    const auto support=fractional_support(s.rate,s.rate/50,c.integer_epoch,c.fractional_offset);
    ++derivations_;
    entries_[next_]={true,s.rate,c.integer_epoch,c.fractional_offset,support};
    next_=(next_+1)%entries_.size();
    finish(s,c,support,out);
    return true;
}

SupportProjectionStatus project(
    const ProjectionSource& source,
    const FractionalCandidate& candidate,
    const SupportDerivationPort& port,
    Observation& observation,
    SupportDerivation& derivation,
    double gate) {
    if(classify(source,candidate,gate)==ProjectionInputStatus::nonpassing)
        return SupportProjectionStatus::nonpassing;
    if(!port.derive) return SupportProjectionStatus::derivation_unavailable;
    SupportDerivation pending;
    SupportDerivationStatus status=SupportDerivationStatus::unavailable;
    try {
        status=port.derive(port.context,source.rate,source.rate/50,
            candidate.integer_epoch,candidate.fractional_offset,&pending);
    } catch(const std::invalid_argument&) {
        return SupportProjectionStatus::invalid_derivation;
    } catch(...) {
        return SupportProjectionStatus::derivation_unavailable;
    }
    if(status==SupportDerivationStatus::invalid_input)
        return SupportProjectionStatus::invalid_derivation;
    if(status!=SupportDerivationStatus::ok)
        return SupportProjectionStatus::derivation_unavailable;
    if(!valid_derivation(pending,source.rate/50))
        return SupportProjectionStatus::invalid_derivation;
    Observation output;
    finish(source,candidate,pending.numeric,output);
    observation=std::move(output);
    derivation=std::move(pending);
    return SupportProjectionStatus::emitted;
}
} }
