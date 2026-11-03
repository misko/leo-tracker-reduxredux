#include "session.hpp"
#include <algorithm>
#include <chrono>
#include <limits>
#include <stdexcept>
namespace leo::adaptive::application {
namespace {
bool digest(const std::string& value) {
    return value.size()==71 && value.compare(0,7,"sha256:")==0 &&
        value.find_first_not_of("0123456789abcdef",7)==std::string::npos;
}
bool profile_name(const std::string& value) {
    if(value.empty() || value.size()>128) return false;
    return std::all_of(value.begin(),value.end(),[](unsigned char character) {
        return (character>='a' && character<='z') ||
            (character>='A' && character<='Z') ||
            (character>='0' && character<='9') || character=='-' || character=='_' ||
            character=='.' || character=='+';
    });
}
}
Session::Session(ingest::Authority authority, timing::Config clock,
                 online::Config analysis, online::SessionAuthority session,
                 std::size_t capacity)
    : authority_(std::move(authority)), timing_(clock),
      coordinator_(analysis,std::move(session)), capacity_(capacity) {
    if(!capacity || capacity>40000 || authority_.sample_rate_hz!=clock.sample_rate_hz ||
       timing_.begin(authority_.generation)!=timing::Status::ok ||
       coordinator_.replace_stream_generation(authority_.generation)!=online::Status::ok)
        throw std::invalid_argument("invalid application session authority");
}
Session::Session(ingest::Authority authority, timing::Config clock,
                 online::Config analysis, online::SessionAuthority session,
                 std::size_t capacity, const SupportDerivationPort& support)
    : authority_(std::move(authority)), timing_(clock),
      coordinator_(analysis,std::move(session)), capacity_(capacity),
      support_binding_{std::string(support.profile_name),
          std::string(support.profile_manifest_digest)},
      support_context_(support.context), support_derive_(support.derive) {
    if(!capacity || capacity>40000 || authority_.sample_rate_hz!=clock.sample_rate_hz ||
       !support_context_ || !support_derive_ ||
       !profile_name(support_binding_.profile_name) ||
       !digest(support_binding_.profile_manifest_digest) ||
       timing_.begin(authority_.generation)!=timing::Status::ok ||
       coordinator_.replace_stream_generation(authority_.generation)!=online::Status::ok)
        throw std::invalid_argument("invalid profiled application session authority");
}
timing::Status Session::observe(const timing::Bracket& b) {
    std::lock_guard<std::mutex> lock(mutex_);
    return timing_.observe(b);
}
AcceptReceipt Session::accept(const leo_scanner_event& event) {
    std::lock_guard<std::mutex> lock(mutex_);
    Pending value;
    const bool deferred=support_derive_;
    if(deferred && support_unhealthy_) {
        ++stats_.rejected_after_support_failure;
        return {ingest::Status::invalid_event,false,false};
    }
    const auto status=deferred ?
        ingest::prepare_event(authority_,timing_,event,value.prepared) :
        ingest::project_event(authority_,timing_,event,value.observation);
    switch(status) {
    case ingest::Status::emitted: {
        if(deferred) ++stats_.profile_prepared;
        else ++stats_.projected;
        if(pending_.size()==capacity_) {
            ++stats_.queue_dropped; return {status,false,false};
        }
        if(!deferred) {
            // Support end is a conservative causal watermark: this observation
            // physically exists by then. Never use an assumed current UTC clock.
            value.watermark=value.observation.support_end_utc_ns;
        }
        value.deferred=deferred;
        pending_.push_back(std::move(value));
        stats_.high_water=std::max(stats_.high_water,pending_.size());
        break;
    }
    case ingest::Status::nonpassing: ++stats_.nonpassing; break;
    case ingest::Status::invalid_event: ++stats_.invalid; break;
    case ingest::Status::timing_unavailable: ++stats_.timing_unavailable; break;
    case ingest::Status::ignored: break;
    }
    const bool queued=status==ingest::Status::emitted;
    return {status,queued,queued && deferred};
}

ConsumeReceipt Session::consume_reported(std::size_t maximum) {
    ConsumeReceipt receipt;
    for(;receipt.dequeued<maximum;) {
        Pending value;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if(support_unhealthy_) {
                receipt.status=ConsumeStatus::unhealthy;
                return receipt;
            }
            if(support_derivation_inflight_) {
                receipt.status=ConsumeStatus::busy;
                return receipt;
            }
            if(pending_.empty()) break;
            value=std::move(pending_.front());pending_.pop_front();
            if(value.deferred) {
                support_derivation_inflight_=true;
                stats_.support_derivation_inflight=true;
            }
        }
        ++receipt.dequeued;
        if(receipt.status==ConsumeStatus::empty) receipt.status=ConsumeStatus::ok;
        pipeline::SupportAuthority support;
        const auto fail_deferred=[&](ConsumeStatus failure) {
            std::lock_guard<std::mutex> lock(mutex_);
            support_derivation_inflight_=false;
            support_unhealthy_=true;
            stats_.support_derivation_inflight=false;stats_.support_unhealthy=true;
            if(failure==ConsumeStatus::support_invalid) ++stats_.support_invalid;
            else if(failure==ConsumeStatus::support_unavailable) ++stats_.support_unavailable;
            stats_.discarded_after_support_failure+=pending_.size();
            pending_.clear();receipt.status=failure;
        };
        if(value.deferred) {
            SupportDerivation derivation;
            const auto started=std::chrono::steady_clock::now();
            SupportProjectionStatus projected=SupportProjectionStatus::derivation_unavailable;
            try {
                projected=project(value.prepared.source,value.prepared.candidate,
                    {support_context_,support_binding_.profile_name,
                        support_binding_.profile_manifest_digest,support_derive_},
                    value.observation,derivation);
            } catch(const std::invalid_argument&) {
                projected=SupportProjectionStatus::invalid_derivation;
            } catch(const std::overflow_error&) {
                projected=SupportProjectionStatus::invalid_derivation;
            } catch(...) {
                projected=SupportProjectionStatus::derivation_unavailable;
            }
            const auto elapsed=static_cast<std::uint64_t>(std::chrono::duration_cast<
                std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count());
            {
                std::lock_guard<std::mutex> lock(mutex_);
                ++stats_.support_derivation_count;
                stats_.support_derivation_max_ns=std::max(
                    stats_.support_derivation_max_ns,elapsed);
                if(std::numeric_limits<std::uint64_t>::max()-
                        stats_.support_derivation_total_ns<elapsed)
                    stats_.support_derivation_total_ns=
                        std::numeric_limits<std::uint64_t>::max();
                else stats_.support_derivation_total_ns+=elapsed;
            }
            if(projected!=SupportProjectionStatus::emitted) {
                const auto failure=projected==SupportProjectionStatus::invalid_derivation ||
                    projected==SupportProjectionStatus::nonpassing ?
                    ConsumeStatus::support_invalid : ConsumeStatus::support_unavailable;
                fail_deferred(failure);
                return receipt;
            }
            value.watermark=value.observation.support_end_utc_ns;
            try {
                support={value.observation.support_start_utc_ns,
                    value.observation.support_center_utc_ns,
                    value.observation.support_end_utc_ns,
                    derivation.factorial_moment_lexemes[0],
                    derivation.factorial_moment_lexemes[1],
                    derivation.factorial_moment_lexemes[2],
                    derivation.factorial_moment_lexemes[3]};
            } catch(...) {
                fail_deferred(ConsumeStatus::support_unavailable);
                return receipt;
            }
            std::lock_guard<std::mutex> lock(mutex_);
            ++stats_.support_derived;++stats_.projected;
        }
        // Detector completion may reorder observations relative to their
        // physical supports. Evidence watermark remains nondecreasing.
        const auto watermark=std::max(
            value.watermark,coordinator_.causal_watermark_utc_ns());
        online::IngestReceipt result;
        try {
            result=value.deferred ?
                coordinator_.ingest(value.observation,support,watermark) :
                coordinator_.ingest(value.observation,watermark);
        } catch(...) {
            if(!value.deferred) throw;
            fail_deferred(ConsumeStatus::support_unavailable);
            return receipt;
        }
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if(value.deferred) {
                support_derivation_inflight_=false;
                stats_.support_derivation_inflight=false;
            }
            if(result.status==online::Status::ok) {
                ++stats_.consumed;++receipt.ingested;
            } else {
                ++stats_.rejected;receipt.status=ConsumeStatus::coordinator_rejected;
                if(value.deferred) {
                    support_unhealthy_=true;
                    stats_.support_unhealthy=true;
                    stats_.discarded_after_support_failure+=pending_.size();
                    pending_.clear();
                }
            }
            stats_.history_capacity_evictions=coordinator_.history_capacity_evictions();
        }
        if(value.deferred && result.status!=online::Status::ok) return receipt;
    }
    return receipt;
}

std::size_t Session::consume(std::size_t maximum) {
    const auto receipt=consume_reported(maximum);
    if(support_derive_ && receipt.status!=ConsumeStatus::empty &&
       receipt.status!=ConsumeStatus::ok)
        throw std::runtime_error("profiled support consumption failed");
    return receipt.dequeued;
}
online::Status Session::publish(std::shared_ptr<const online::Snapshot>* out) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if(!pending_.empty() || support_derivation_inflight_ || support_unhealthy_)
            return online::Status::invalid;
    }
    return coordinator_.publish(coordinator_.causal_watermark_utc_ns(),out);
}
online::Status Session::advance_watermark(std::int64_t utc) {
    std::lock_guard<std::mutex> lock(mutex_);
    // Drain already accepted evidence before quiet-source expiry. Otherwise a
    // queued observation can be counted as consumed and immediately pruned.
    if(!pending_.empty() || support_derivation_inflight_ || support_unhealthy_)
        return online::Status::invalid;
    return coordinator_.advance_watermark(utc);
}
std::int64_t Session::watermark() const { return coordinator_.causal_watermark_utc_ns(); }
online::Status Session::replace_orbit(const online::OrbitBuild& b) { return coordinator_.replace_orbit(b); }
online::Status Session::begin_search(std::uint64_t g,const online::SearchConfig& c,online::SearchResult* r) {
    return coordinator_.begin_search(g,c,r);
}
online::SearchResult Session::resume_search(std::uint32_t n) { return coordinator_.resume_search(n); }
online::SearchResult Session::cancel_search() { return coordinator_.cancel_search(); }
Stats Session::stats() const {
    std::lock_guard<std::mutex> lock(mutex_);auto copy=stats_;copy.queued=pending_.size();return copy;
}
online::ExactScoreCacheStats Session::exact_score_cache_stats() const {
    return coordinator_.exact_score_cache_stats();
}
const SupportProfileBinding* Session::support_profile_binding() const noexcept {
    return support_derive_ ? &support_binding_ : nullptr;
}
}
