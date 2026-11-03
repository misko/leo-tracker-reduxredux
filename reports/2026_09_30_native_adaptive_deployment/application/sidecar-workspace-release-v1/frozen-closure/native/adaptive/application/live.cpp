#include "live.hpp"
#include "../timing/posix_clock.hpp"
#include "../device/local/local_radio_prepare.h"
#include "../location/tle_id.hpp"
#include "../runtime/sha256.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <mutex>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <time.h>
#include <unordered_set>
#include <utility>

namespace leo::adaptive::application::live {
namespace {

[[maybe_unused]] bool tagged_digest(const std::string& value) {
    return value.size()==71 && value.compare(0,7,"sha256:")==0 &&
        value.find_first_not_of("0123456789abcdef",7)==std::string::npos;
}

std::int64_t bracket_frontier(const timing::Bracket& bracket,std::uint64_t lateness) {
    if (bracket.utc_before_ns<=0 || lateness>static_cast<std::uint64_t>(INT64_MAX) ||
        bracket.utc_before_ns<=static_cast<std::int64_t>(lateness)) return 0;
    return bracket.utc_before_ns-static_cast<std::int64_t>(lateness);
}

online::Config bind_analysis_execution(const AnalysisConfig& config,
                                       TrackingExecution& execution) {
    auto online=config.online;
    if (config.analysis_workers>1U) {
        if (online.tracking_execution.run || online.scoring_execution.run ||
            online.scoring_execution.context ||
            online.scoring_execution.workers!=1U)
            throw std::invalid_argument("owned and external analysis execution conflict");
        const auto port=execution.port();
        online.tracking_execution=port;
        // Publication and scoring execute sequentially on the analysis owner.
        // Both borrowed ports therefore reuse one bounded pool, without nesting.
        online.scoring_execution={config.analysis_workers,port.context,port.run};
    }
    return online;
}

bool empty_support_port(const SupportDerivationPort& port) {
    return port.context==nullptr && port.profile_name.empty() &&
        port.profile_manifest_digest.empty() && port.derive==nullptr;
}

bool support_profile_name(std::string_view value) {
    return !value.empty() && value.size()<=128 &&
        std::all_of(value.begin(),value.end(),[](unsigned char character) {
            return (character>='a' && character<='z') ||
                (character>='A' && character<='Z') ||
                (character>='0' && character<='9') || character=='-' ||
                character=='_' || character=='.' || character=='+';
        });
}

bool valid_support_port(const SupportDerivationPort& port) {
    return port.context!=nullptr && port.derive!=nullptr &&
        support_profile_name(port.profile_name) &&
        tagged_digest(std::string(port.profile_manifest_digest));
}

std::unique_ptr<application::Session> make_session(
    AnalysisConfig& config,TrackingExecution& execution) {
    auto online=bind_analysis_execution(config,execution);
    if (empty_support_port(config.support_derivation)) {
        return std::make_unique<application::Session>(config.authority,config.timing,
            std::move(online),config.session,4096);
    }
    if (!valid_support_port(config.support_derivation))
        throw std::invalid_argument("malformed live support derivation binding");
    return std::make_unique<application::Session>(config.authority,config.timing,
        std::move(online),config.session,4096,config.support_derivation);
}

} // namespace

struct Analysis::Impl {
    explicit Impl(AnalysisConfig value)
        : config(std::move(value)), tracking_execution(config.analysis_workers),
          session(make_session(config,tracking_execution)) {
        if (config.catalogue.empty() || config.catalogue.size()>config.online.maximum_satellites ||
            !config.maximum_detector_latency_ns || !config.publication_interval_ns ||
            config.maximum_detector_latency_ns>=
                static_cast<std::uint64_t>(config.online.history_window_ns) ||
            config.publication_interval_ns>static_cast<std::uint64_t>(INT64_MAX) ||
            !config.search_slice_points || !std::isfinite(config.orbit_knot_step_s) ||
            config.orbit_knot_step_s<=0 || config.orbit_knot_count<2 ||
            config.orbit_knot_count>config.online.maximum_knots)
            throw std::invalid_argument("invalid live analysis configuration");
        if (const auto* binding=session->support_profile_binding()) {
            summary.support_profile_bound=true;
            summary.support_profile=*binding;
            published_summary=summary;
        }
        // Session copied the metadata and borrowed callback/context. Retaining
        // the caller's string_views in the long-lived config would add no
        // authority and could leave dangling views after construction.
        config.support_derivation={};
        if (!config.caller_driven) worker=std::thread(&Impl::work,this);
    }

    ~Impl() {
        {
            std::lock_guard<std::mutex> lock(mutex);
            done=true;
        }
        changed.notify_one();
        if (worker.joinable()) worker.join();
    }

    void cancel_source() {
        std::lock_guard<std::mutex> lock(cancel_mutex);
        if (cancel) (void)cancel(cancel_context);
    }

    static std::uint64_t nonnegative_age(std::int64_t newer,std::int64_t older) {
        if (newer<=older) return 0;
        if (older>=0)
            return static_cast<std::uint64_t>(newer)-static_cast<std::uint64_t>(older);
        return static_cast<std::uint64_t>(newer)+
            static_cast<std::uint64_t>(-(older+1))+1;
    }

    std::pair<std::int64_t,std::int64_t> measured_source_progress() {
        std::lock_guard<std::mutex> lock(mutex);
        return {latest_source_progress_before,latest_source_progress_after};
    }

    void add_publication_duration(std::uint64_t duration) {
        ++summary.publication_compute_count;
        summary.publication_compute_max_ns=std::max(summary.publication_compute_max_ns,duration);
        if (UINT64_MAX-summary.publication_compute_total_ns<duration)
            summary.publication_compute_total_ns=UINT64_MAX;
        else summary.publication_compute_total_ns+=duration;
    }

    void build_or_reuse_orbit(const online::Snapshot& snapshot) {
        if (snapshot.location_tracks.records.empty()) return;
        double required_first=std::numeric_limits<double>::infinity();
        double required_last=-std::numeric_limits<double>::infinity();
        for (const auto& track:snapshot.location_tracks.records) {
            if (!track.observation_count) throw std::runtime_error("empty location track");
            required_first=std::min(required_first,
                track.times_s[0]+config.search.score.tau_first_s-config.orbit_knot_step_s);
            required_last=std::max(required_last,
                track.times_s[track.observation_count-1]+config.search.score.tau_last_s+
                    config.orbit_knot_step_s);
        }
        if (orbit_generation && required_first>=orbit_first && required_last<=orbit_last) return;
        const double first=std::floor(required_first/config.orbit_knot_step_s)*
            config.orbit_knot_step_s;
        const double last=first+(config.orbit_knot_count-1)*config.orbit_knot_step_s;
        if (!(required_last<=last)) throw std::runtime_error("retained evidence exceeds orbit window");
        online::OrbitBuild build{};
        build.generation=++orbit_generation;
        build.start_utc_ns=config.session.session_start_utc_ns;
        build.knot_start_s=first; build.knot_step_s=config.orbit_knot_step_s;
        build.knot_count=config.orbit_knot_count;
        build.records=config.catalogue;
        if (session->replace_orbit(build)!=online::Status::ok)
            throw std::runtime_error("live orbit build failed");
        orbit_first=first; orbit_last=last; ++summary.orbit_builds;
        summary.orbit_generation=orbit_generation;
    }

    bool publish_and_search(std::int64_t watermark) {
        std::shared_ptr<const online::Snapshot> snapshot;
        const auto begun=std::chrono::steady_clock::now();
        const auto status=session->publish(&snapshot);
        const auto duration=static_cast<std::uint64_t>(std::chrono::duration_cast<
            std::chrono::nanoseconds>(std::chrono::steady_clock::now()-begun).count());
        add_publication_duration(duration);
        if (status==online::Status::no_observations) {
            ++summary.publication_empty; last_publication_watermark=watermark; return true;
        }
        if (status==online::Status::invalid && session->stats().queued>0) {
            ++summary.publication_deferrals;
            return false;
        }
        if (status!=online::Status::ok || !snapshot) {
            ++summary.publication_failures; return false;
        }
        if (config.online.publication_search_policy==
                online::PublicationSearchPolicy::invalidate_on_publish) {
            search_running=false;
            summary.last_search={};
        }
        ++summary.publications; summary.snapshot_generation=snapshot->generation;
        last_publication_watermark=snapshot->watermark_utc_ns;
        summary.last_snapshot_watermark_utc_ns=snapshot->watermark_utc_ns;
        const auto progress=measured_source_progress();
        const auto snapshot_age_lower=nonnegative_age(progress.first,snapshot->watermark_utc_ns);
        const auto snapshot_age_upper=nonnegative_age(progress.second,snapshot->watermark_utc_ns);
        ++summary.snapshot_source_age_count;
        summary.snapshot_source_age_lower_current_ns=snapshot_age_lower;
        summary.snapshot_source_age_lower_max_ns=std::max(
            summary.snapshot_source_age_lower_max_ns,snapshot_age_lower);
        summary.snapshot_source_age_upper_current_ns=snapshot_age_upper;
        summary.snapshot_source_age_upper_max_ns=std::max(
            summary.snapshot_source_age_upper_max_ns,snapshot_age_upper);
        pending_search_snapshot.reset();
        if (snapshot->location_tracks.records.empty()) return true;
        ++summary.publications_with_tracks;
        pending_search_snapshot=std::move(snapshot);
        pending_publication_started=begun;
        start_pending_search();
        return true;
    }

    void start_pending_search() {
        if (search_running || !pending_search_snapshot) return;
        auto snapshot=std::move(pending_search_snapshot);
        const auto watermark=session->watermark();
        if (watermark>snapshot->watermark_utc_ns &&
            watermark-snapshot->watermark_utc_ns>config.online.history_window_ns) {
            ++summary.searches_stale;
            return;
        }
        // Orbit replacement invalidates pinned searches, so defer any rebuild
        // until the previous search finishes or explicitly becomes stale.
        build_or_reuse_orbit(*snapshot);
        online::SearchResult started{};
        const auto begin=session->begin_search(snapshot->generation,config.search,&started);
        if (begin!=online::Status::ok) { ++summary.search_failures; return; }
        ++summary.searches_started; search_running=true;
        search_snapshot_watermark=snapshot->watermark_utc_ns;
        search_publication_started=pending_publication_started;
    }

    void process(bool final) {
        // The Session wrapper preserves portable rejection accounting and
        // throws on every non-successful profiled consumption. record_failure
        // snapshots the resulting unhealthy profile statistics before cancel.
        while (session->consume(256)) {}
        std::int64_t frontier=0,source_progress_before=0,source_progress_after=0,
            first_progress=0;
        {
            std::lock_guard<std::mutex> lock(mutex);
            frontier=latest_frontier;
            source_progress_before=latest_source_progress_before;
            source_progress_after=latest_source_progress_after;
            first_progress=first_source_progress;
            summary.latest_measured_source_progress_utc_before_ns=source_progress_before;
            summary.latest_measured_source_progress_utc_after_ns=source_progress_after;
        }
        summary.latest_causal_frontier_utc_ns=frontier;
        const auto previous=session->watermark();
        bool watermark_deferred=false;
        if (frontier>previous) {
            const auto status=session->advance_watermark(frontier);
            if (status==online::Status::invalid && session->stats().queued>0) {
                ++summary.watermark_deferrals; watermark_deferred=true;
            } else if (status!=online::Status::ok) ++summary.publication_failures;
        }
        const auto watermark=session->watermark();
        if (last_publication_watermark>0 &&
            watermark-last_publication_watermark>config.online.history_window_ns &&
            !snapshot_expired) {
            ++summary.snapshot_expirations; snapshot_expired=true;
        }
        if (!next_cadence_source_utc && first_progress>0) {
            const auto interval=static_cast<std::int64_t>(config.publication_interval_ns);
            next_cadence_source_utc=first_progress>INT64_MAX-interval ?
                INT64_MAX : first_progress+interval;
        }
        std::uint64_t cadence_due=0;
        if (next_cadence_source_utc>0 && source_progress_before>=next_cadence_source_utc) {
            cadence_due=1+static_cast<std::uint64_t>(
                source_progress_before-next_cadence_source_utc)/config.publication_interval_ns;
            if (UINT64_MAX-summary.publication_cadence_requests<cadence_due)
                summary.publication_cadence_requests=UINT64_MAX;
            else summary.publication_cadence_requests+=cadence_due;
            const auto missed=cadence_due-(cadence_pending ? 0 : 1);
            if (UINT64_MAX-summary.publication_cadence_misses<missed)
                summary.publication_cadence_misses=UINT64_MAX;
            else summary.publication_cadence_misses+=missed;
            cadence_pending=true;
            const auto available=static_cast<std::uint64_t>(
                INT64_MAX-next_cadence_source_utc);
            next_cadence_source_utc=cadence_due>available/config.publication_interval_ns ?
                INT64_MAX : next_cadence_source_utc+static_cast<std::int64_t>(
                    cadence_due*config.publication_interval_ns);
        }
        const bool bootstrap=!publication_bootstrapped && watermark>0;
        if (!watermark_deferred &&
            (bootstrap || cadence_pending || (final && watermark>last_publication_watermark)) &&
            watermark>0 && (bootstrap || watermark>last_publication_watermark)) {
            if (publish_and_search(watermark)) {
                publication_bootstrapped=true;
                if (cadence_pending) {
                    cadence_pending=false;
                    ++summary.publication_cadence_serviced;
                }
                if (last_publication_watermark>0) snapshot_expired=false;
            }
        }
        start_pending_search();
        if (search_running) {
            const auto result=session->resume_search(config.search_slice_points);
            summary.last_search=result;
            if (result.state==online::SearchState::complete) {
                ++summary.searches_complete; search_running=false;
                summary.last_result_snapshot_watermark_utc_ns=search_snapshot_watermark;
                const auto progress=measured_source_progress();
                const auto result_age_lower=nonnegative_age(progress.first,
                    search_snapshot_watermark);
                const auto result_age_upper=nonnegative_age(progress.second,
                    search_snapshot_watermark);
                ++summary.result_source_age_count;
                summary.result_source_age_lower_current_ns=result_age_lower;
                summary.result_source_age_lower_max_ns=std::max(
                    summary.result_source_age_lower_max_ns,result_age_lower);
                summary.result_source_age_upper_current_ns=result_age_upper;
                summary.result_source_age_upper_max_ns=std::max(
                    summary.result_source_age_upper_max_ns,result_age_upper);
                const auto result_duration=static_cast<std::uint64_t>(
                    std::chrono::duration_cast<std::chrono::nanoseconds>(
                        std::chrono::steady_clock::now()-search_publication_started).count());
                ++summary.snapshot_result_duration_count;
                summary.snapshot_result_duration_current_ns=result_duration;
                summary.snapshot_result_duration_max_ns=std::max(
                    summary.snapshot_result_duration_max_ns,result_duration);
            } else if (result.state==online::SearchState::running_unconverged) {
                ++summary.searches_unconverged;
            } else if (result.state==online::SearchState::stale) {
                ++summary.searches_stale; search_running=false;
            } else {
                ++summary.search_failures; search_running=false;
            }
        }
        summary.causal_watermark_utc_ns=session->watermark();
        summary.publication_cadence_pending=cadence_pending;
        if (summary.last_snapshot_watermark_utc_ns>0) {
            summary.publication_lag_current_ns=nonnegative_age(frontier,
                summary.last_snapshot_watermark_utc_ns);
            summary.publication_lag_max_ns=std::max(summary.publication_lag_max_ns,
                summary.publication_lag_current_ns);
        }
        summary.session=session->stats();
        summary.exact_score_cache=session->exact_score_cache_stats();
        summary.search_pending=static_cast<bool>(pending_search_snapshot);
        {
            std::lock_guard<std::mutex> lock(mutex);
            published_summary=summary;
        }
    }

    void record_failure() {
        summary.session=session->stats();
        summary.exact_score_cache=session->exact_score_cache_stats();
        {
            std::lock_guard<std::mutex> lock(mutex);
            failure=std::current_exception(); summary.timing_qualified=false;
            published_summary=summary;
        }
        cancel_source();
    }

    void work() {
        try {
            for (;;) {
                bool stop=false;
                {
                    std::unique_lock<std::mutex> lock(mutex);
                    const auto observed=sequence;
                    changed.wait_for(lock,std::chrono::milliseconds(100),[&] {
                        return done || sequence!=observed;
                    });
                    stop=done;
                }
                process(stop);
                if (stop) break;
            }
        } catch (...) {
            record_failure();
        }
    }

    AnalysisConfig config;
    TrackingExecution tracking_execution;
    std::unique_ptr<application::Session> session;
    std::mutex mutex;
    std::mutex cancel_mutex;
    std::condition_variable changed;
    std::uint64_t sequence{};
    std::int64_t latest_frontier{};
    std::int64_t latest_source_progress_before{},latest_source_progress_after{};
    std::int64_t first_source_progress{};
    void* cancel_context{};
    int (*cancel)(void*){};
    bool done{},finished{},polling{},search_running{},snapshot_expired{};
    bool cadence_pending{},publication_bootstrapped{};
    std::exception_ptr failure;
    std::thread worker;
    Summary summary;
    Summary published_summary;
    std::uint64_t orbit_generation{};
    double orbit_first{},orbit_last{};
    std::int64_t last_publication_watermark{},next_cadence_source_utc{};
    std::int64_t search_snapshot_watermark{};
    std::chrono::steady_clock::time_point search_publication_started{};
    std::shared_ptr<const online::Snapshot> pending_search_snapshot;
    std::chrono::steady_clock::time_point pending_publication_started{};
};

Analysis::Analysis(AnalysisConfig config):impl_(std::make_unique<Impl>(std::move(config))) {}
Analysis::~Analysis()=default;

timing::Status Analysis::observe(const timing::Bracket& bracket) {
    const auto status=impl_->session->observe(bracket);
    bool cancel=false;
    {
        std::lock_guard<std::mutex> lock(impl_->mutex);
        if (status!=timing::Status::ok) {
            ++impl_->summary.timing_failures; impl_->summary.timing_qualified=false; cancel=true;
        } else {
            impl_->latest_frontier=std::max(impl_->latest_frontier,
                bracket_frontier(bracket,impl_->config.maximum_detector_latency_ns));
            if (bracket.utc_before_ns>=impl_->latest_source_progress_before) {
                impl_->latest_source_progress_before=bracket.utc_before_ns;
                impl_->latest_source_progress_after=bracket.utc_after_ns;
            }
            if (!impl_->first_source_progress)
                impl_->first_source_progress=bracket.utc_before_ns;
            ++impl_->sequence;
        }
    }
    impl_->changed.notify_one();
    if (cancel) impl_->cancel_source();
    return status;
}

void Analysis::event(const leo_scanner_event& event) {
    bool cancel=false;
    if (event.kind==LEO_SCANNER_QUEUE_DROP || event.kind==LEO_SCANNER_DETECTOR_FAILURE) {
        std::lock_guard<std::mutex> lock(impl_->mutex);
        if (event.kind==LEO_SCANNER_QUEUE_DROP) ++impl_->summary.scanner_queue_drops;
        else ++impl_->summary.detector_failures;
        impl_->summary.timing_qualified=false; cancel=true;
    }
    const bool detector_delivery=event.kind==LEO_SCANNER_DETECTOR_RESULT ||
        event.kind==LEO_SCANNER_DETECTOR_FAILURE || event.kind==LEO_SCANNER_CANDIDATE;
    bool late=detector_delivery &&
        (!event.detector_enqueued_monotonic_ns || !event.detector_started_monotonic_ns ||
         !event.detector_finished_monotonic_ns ||
         event.detector_started_monotonic_ns<event.detector_enqueued_monotonic_ns ||
         event.detector_finished_monotonic_ns<event.detector_started_monotonic_ns ||
         event.detector_finished_monotonic_ns-event.detector_enqueued_monotonic_ns>
            impl_->config.maximum_detector_latency_ns);
    if (detector_delivery && !late) {
        const auto now=static_cast<std::uint64_t>(std::chrono::duration_cast<
            std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
        if (now<event.detector_enqueued_monotonic_ns ||
            now-event.detector_enqueued_monotonic_ns>
                impl_->config.maximum_detector_latency_ns) late=true;
    }
    if (late) {
        std::lock_guard<std::mutex> lock(impl_->mutex);
        ++impl_->summary.detector_latency_violations;
        impl_->summary.timing_qualified=false; cancel=true;
    }
    if (event.kind==LEO_SCANNER_CANDIDATE) {
        const auto receipt=impl_->session->accept(event);
        std::lock_guard<std::mutex> lock(impl_->mutex);
        ++impl_->summary.scanner_candidates;
        if (receipt.queued) ++impl_->summary.accepted_candidates;
        else ++impl_->summary.rejected_candidates;
        if (receipt.projection==ingest::Status::emitted && !receipt.queued) {
            ++impl_->summary.application_queue_overflows;
            impl_->summary.timing_qualified=false; cancel=true;
        } else if (receipt.projection==ingest::Status::invalid_event) {
            ++impl_->summary.invalid_candidate_events;
            impl_->summary.timing_qualified=false; cancel=true;
        } else if (receipt.projection==ingest::Status::timing_unavailable) {
            ++impl_->summary.timing_failures; impl_->summary.timing_qualified=false; cancel=true;
        }
        ++impl_->sequence;
    }
    impl_->changed.notify_one();
    if (cancel) impl_->cancel_source();
}

void Analysis::set_cancel(void* context,int (*cancel)(void*)) {
    std::lock_guard<std::mutex> lock(impl_->cancel_mutex);
    impl_->cancel_context=context; impl_->cancel=cancel;
}

void Analysis::detach_cancel() {
    std::lock_guard<std::mutex> lock(impl_->cancel_mutex);
    impl_->cancel_context=nullptr; impl_->cancel=nullptr;
}

Summary Analysis::progress() const {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    return impl_->published_summary;
}

Summary Analysis::poll() {
    {
        std::lock_guard<std::mutex> lock(impl_->mutex);
        if (!impl_->config.caller_driven || impl_->finished || impl_->polling)
            throw std::logic_error("analysis poll requires an idle caller-driven owner");
        if (impl_->failure) std::rethrow_exception(impl_->failure);
        impl_->polling=true;
    }
    try { impl_->process(false); }
    catch (...) {
        impl_->record_failure();
        std::lock_guard<std::mutex> lock(impl_->mutex);
        impl_->polling=false;
        throw;
    }
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->polling=false;
    return impl_->published_summary;
}

Summary Analysis::finish_after_rf_stopped() {
    {
        std::lock_guard<std::mutex> lock(impl_->mutex);
        if (impl_->finished || impl_->polling)
            throw std::logic_error("live analysis is finished or being polled");
        impl_->finished=true; impl_->done=true;
    }
    impl_->changed.notify_one();
    if (impl_->config.caller_driven && !impl_->failure) {
        try { impl_->process(true); }
        catch (...) { impl_->record_failure(); }
    }
    if (impl_->worker.joinable()) impl_->worker.join();
    std::lock_guard<std::mutex> lock(impl_->mutex);
    if (impl_->failure) std::rethrow_exception(impl_->failure);
    return impl_->summary;
}

} // namespace leo::adaptive::application::live

#ifndef LEO_LIVE_CORE_ONLY
namespace {
using namespace leo::adaptive;
using namespace leo::adaptive::application::live;

template<class Callback> class ScopeExit {
public:
    explicit ScopeExit(Callback callback):callback_(std::move(callback)) {}
    ~ScopeExit() { run(); }
    ScopeExit(const ScopeExit&)=delete;
    ScopeExit& operator=(const ScopeExit&)=delete;
    void dismiss() { active_=false; }
    void run() { if (active_) { active_=false; callback_(); } }
private:
    Callback callback_;
    bool active_{true};
};

struct Parsed {
    std::uint32_t duration_ms{},maximum_visits{},dwell_ms{},block_ms{};
    std::uint32_t maximum_detector_latency_ms{},publication_ms{},history_seconds{};
    std::uint32_t search_budget{},search_slice{};
    std::uint32_t cpu_workers{2U},detector_workers{1U},analysis_workers{1U};
    std::uint64_t generation{};
    double latitude{},longitude{},radius_km{},region_km{},level_km{};
    std::string exact,control,tles,input_digest,analysis_digest,session_id;
    std::vector<Target> targets;
    bool cpu_workers_set{},detector_workers_set{},analysis_workers_set{};
};

bool unsigned_number(const char* text,std::uint64_t maximum,std::uint64_t& out,
                     bool zero=false) {
    if (!text || !*text || *text=='-') return false;
    errno=0; char* end=nullptr; const auto value=std::strtoull(text,&end,10);
    if (errno || !end || *end || (!zero && !value) || value>maximum) return false;
    out=value; return true;
}

bool finite_number(const char* text,double& out) {
    if (!text || !*text) return false;
    errno=0; char* end=nullptr; out=std::strtod(text,&end);
    return !errno && end && !*end && std::isfinite(out);
}

bool regular_absolute(const std::string& path) {
    if (path.empty() || path.front()!='/') return false;
    struct stat value{}; return !stat(path.c_str(),&value) && S_ISREG(value.st_mode);
}

bool parse(int argc,char** argv,Parsed& out) {
    if (argc<2 || std::strcmp(argv[1],"--capture")) return false;
    bool origin=false;
    for (int i=2;i<argc;) {
        const std::string key=argv[i++]; std::uint64_t value=0;
        auto next=[&]() -> const char* { return i<argc ? argv[i++] : nullptr; };
        if (key=="--duration-ms") {
            if (!unsigned_number(next(),1800000,value) || out.duration_ms) return false;
            out.duration_ms=static_cast<std::uint32_t>(value);
        } else if (key=="--maximum-visits") {
            if (!unsigned_number(next(),16384,value) || out.maximum_visits) return false;
            out.maximum_visits=static_cast<std::uint32_t>(value);
        } else if (key=="--active-dwell-ms") {
            if (!unsigned_number(next(),360,value) || out.dwell_ms ||
                (value!=120 && value!=240 && value!=360)) return false;
            out.dwell_ms=static_cast<std::uint32_t>(value);
        } else if (key=="--block-ms") {
            if (!unsigned_number(next(),120,value) || out.block_ms ||
                (value!=20 && value!=120)) return false;
            out.block_ms=static_cast<std::uint32_t>(value);
        } else if (key=="--maximum-detector-latency-ms") {
            if (!unsigned_number(next(),60000,value) || out.maximum_detector_latency_ms) return false;
            out.maximum_detector_latency_ms=static_cast<std::uint32_t>(value);
        } else if (key=="--publication-ms") {
            if (!unsigned_number(next(),10000,value) || out.publication_ms) return false;
            out.publication_ms=static_cast<std::uint32_t>(value);
        } else if (key=="--history-seconds") {
            if (!unsigned_number(next(),600,value) || out.history_seconds ||
                (value!=10 && value!=600)) return false;
            out.history_seconds=static_cast<std::uint32_t>(value);
        } else if (key=="--cpu-workers") {
            if (!unsigned_number(next(),4U,value) || out.cpu_workers_set) return false;
            out.cpu_workers=static_cast<std::uint32_t>(value); out.cpu_workers_set=true;
        } else if (key=="--detector-workers") {
            if (!unsigned_number(next(),LEO_SCANNER_MAX_DETECTOR_WORKERS,value) ||
                out.detector_workers_set) return false;
            out.detector_workers=static_cast<std::uint32_t>(value);
            out.detector_workers_set=true;
        } else if (key=="--analysis-workers") {
            if (!unsigned_number(next(),4U,value) || out.analysis_workers_set) return false;
            out.analysis_workers=static_cast<std::uint32_t>(value);
            out.analysis_workers_set=true;
        } else if (key=="--generation") {
            if (!unsigned_number(next(),UINT64_MAX,value) || out.generation) return false;
            out.generation=value;
        } else if (key=="--exact-template") {
            const char* value_text=next(); if (!value_text || !out.exact.empty()) return false;
            out.exact=value_text;
        } else if (key=="--control-template") {
            const char* value_text=next(); if (!value_text || !out.control.empty()) return false;
            out.control=value_text;
        } else if (key=="--tle-catalogue") {
            const char* value_text=next(); if (!value_text || !out.tles.empty()) return false;
            out.tles=value_text;
        } else if (key=="--input-digest") {
            const char* value_text=next(); if (!value_text || !out.input_digest.empty()) return false;
            out.input_digest=value_text;
        } else if (key=="--analysis-digest") {
            const char* value_text=next(); if (!value_text || !out.analysis_digest.empty()) return false;
            out.analysis_digest=value_text;
        } else if (key=="--session-id") {
            const char* value_text=next(); if (!value_text || !out.session_id.empty()) return false;
            out.session_id=value_text;
        }
        else if (key=="--search-origin") {
            if (origin || i+1>=argc || !finite_number(argv[i++],out.latitude) ||
                !finite_number(argv[i++],out.longitude)) return false;
            origin=true;
        } else if (key=="--search-radius-km") {
            if (out.radius_km!=0 || !finite_number(next(),out.radius_km)) return false;
        } else if (key=="--search-region-km") {
            if (out.region_km!=0 || !finite_number(next(),out.region_km)) return false;
        } else if (key=="--search-level-km") {
            if (out.level_km!=0 || !finite_number(next(),out.level_km)) return false;
        } else if (key=="--search-point-budget") {
            if (!unsigned_number(next(),100000,value) || out.search_budget) return false;
            out.search_budget=static_cast<std::uint32_t>(value);
        } else if (key=="--search-slice-points") {
            if (!unsigned_number(next(),100000,value) || out.search_slice) return false;
            out.search_slice=static_cast<std::uint32_t>(value);
        } else if (key=="--target") {
            if (i+4>=argc || out.targets.size()==LEO_SCANNER_MAX_TARGETS) return false;
            Target target; std::uint64_t profile=0,frequency=0,channel=0;
            if (!unsigned_number(argv[i++],7,profile,true) ||
                !unsigned_number(argv[i++],UINT64_MAX,frequency) ||
                !unsigned_number(argv[i++],4,channel) || channel<1) return false;
            const std::string edge=argv[i++];
            if (edge=="upper") target.upper_edge=true;
            else if (edge!="lower") return false;
            if (!finite_number(argv[i++],target.actual_rf_hz) || target.actual_rf_hz<=0 ||
                frequency<70000000 || frequency>6000000000ULL) return false;
            target.profile=static_cast<std::uint32_t>(profile);
            target.frequency_hz=frequency; target.channel=static_cast<std::uint32_t>(channel);
            out.targets.push_back(target);
        } else return false;
    }
    for (std::size_t i=0;i<out.targets.size();++i) for (std::size_t j=0;j<i;++j)
        if (out.targets[i].profile==out.targets[j].profile ||
            (out.targets[i].channel==out.targets[j].channel &&
             out.targets[i].upper_edge==out.targets[j].upper_edge &&
             out.targets[i].actual_rf_hz==out.targets[j].actual_rf_hz)) return false;
    const double grid_count=out.region_km/out.level_km;
    const application::ExecutionBudget execution{out.cpu_workers,out.detector_workers,
        out.analysis_workers};
    return execution.valid(application::ExecutionMode::live) &&
        out.duration_ms && out.maximum_visits && out.dwell_ms && out.block_ms &&
        out.maximum_detector_latency_ms && out.publication_ms &&
        (out.history_seconds==10 || out.history_seconds==600) &&
        out.maximum_detector_latency_ms<out.history_seconds*1000U &&
        out.generation && origin && out.latitude>=-90 && out.latitude<=90 &&
        out.longitude>=-180 && out.longitude<=180 && out.radius_km>0 && out.radius_km<=500 &&
        out.region_km>0 && out.region_km<=1000 && out.radius_km<=out.region_km/2 &&
        out.level_km>0 && grid_count>=1 && grid_count<=100 &&
        std::abs(grid_count-std::round(grid_count))<=1e-12 &&
        out.search_budget && out.search_slice &&
        out.search_slice<=out.search_budget && !out.session_id.empty() &&
        out.session_id.size()<=128 &&
        tagged_digest(out.input_digest) && tagged_digest(out.analysis_digest) &&
        regular_absolute(out.exact) && regular_absolute(out.control) &&
        regular_absolute(out.tles) && !out.targets.empty();
}

template<class T> std::vector<T> read_exact(const std::string& path,std::size_t count) {
    std::vector<T> values(count); std::ifstream input(path,std::ios::binary);
    input.read(reinterpret_cast<char*>(values.data()),
        static_cast<std::streamsize>(values.size()*sizeof(T)));
    if (!input || input.peek()!=std::ifstream::traits_type::eof())
        throw std::runtime_error("template size/read failure");
    return values;
}

std::vector<leo_tle_record> read_tles(const std::string& path) {
    std::ifstream input(path); std::size_t count=0;
    if (!(input>>count) || !count || count>20000) throw std::runtime_error("bad TLE count");
    input.ignore(1024,'\n'); std::vector<leo_tle_record> result(count);
    std::unordered_set<std::int32_t> identifiers;
    for (std::size_t i=0;i<count;++i) {
        std::string one,two; std::getline(input,one); std::getline(input,two);
        if (one.size()!=69 || two.size()!=69 || one[0]!='1' || two[0]!='2')
            throw std::runtime_error("bad TLE record");
        std::int32_t id=0,second_id=0;
        if (!location::parse_tle_catalogue_id(std::string_view(one).substr(2,5),id) ||
            !location::parse_tle_catalogue_id(std::string_view(two).substr(2,5),second_id) ||
            id!=second_id || !identifiers.insert(id).second)
            throw std::runtime_error("inconsistent TLE satellite id");
        result[i].satellite_id=id;
        std::memcpy(result[i].line1,one.data(),69); std::memcpy(result[i].line2,two.data(),69);
        result[i].line1[69]=result[i].line2[69]='\0';
    }
    std::string extra; while (std::getline(input,extra)) if (!extra.empty())
        throw std::runtime_error("trailing TLE data");
    return result;
}

int monotonic_ns(std::uint64_t& value) {
    timespec now{}; if (clock_gettime(CLOCK_MONOTONIC,&now)) return -errno;
    value=static_cast<std::uint64_t>(now.tv_sec)*1000000000ULL+now.tv_nsec; return 0;
}

std::pair<double,double> offset_coordinate(double latitude_deg,double longitude_deg,
                                           double east_km,double north_km) {
    constexpr double pi=3.141592653589793238462643383279502884;
    constexpr double radius_km=6371.0088;
    const double angular=std::hypot(east_km,north_km)/radius_km;
    const double bearing=std::atan2(east_km,north_km);
    const double latitude0=latitude_deg*pi/180.0;
    const double longitude0=longitude_deg*pi/180.0;
    const double latitude=std::asin(std::sin(latitude0)*std::cos(angular)+
        std::cos(latitude0)*std::sin(angular)*std::cos(bearing));
    double longitude=longitude0+std::atan2(std::sin(bearing)*std::sin(angular)*
        std::cos(latitude0),std::cos(angular)-std::sin(latitude0)*std::sin(latitude));
    longitude=std::remainder(longitude,2*pi);
    return {latitude*180.0/pi,longitude*180.0/pi};
}

int detector_analyze(void* context,const int16_t* iq,size_t times,uint32_t dwell,
                     uint32_t stride,leo_native_glrt_result* result) {
    return leo_native_glrt_analyze(static_cast<leo_native_glrt*>(context),iq,times,dwell,stride,result);
}
int detector_capabilities(void*,leo_native_glrt_capabilities* out) {
    return leo_native_glrt_get_capabilities(out);
}

struct DetectorDeleter {
    void operator()(leo_native_glrt* context) const noexcept {
        if (context) (void)leo_native_glrt_destroy(context);
    }
};
using DetectorOwner=std::unique_ptr<leo_native_glrt,DetectorDeleter>;

void append_u32_le(std::string& value,std::uint32_t number) {
    for (unsigned shift=0;shift<32U;shift+=8U)
        value.push_back(static_cast<char>((number>>shift)&0xffU));
}

std::array<std::uint8_t,32> detector_binding_digest(
    const std::string& analysis_digest,const std::vector<leo_native_glrt_complex>& exact,
    const std::vector<leo_native_glrt_complex>& control,std::uint32_t rate,
    std::uint32_t mode) {
    std::string material="leo-native-live-detector-binding/v1";
    material.push_back('\0'); material.append(analysis_digest); material.push_back('\0');
    append_u32_le(material,rate); append_u32_le(material,mode);
    material.append(reinterpret_cast<const char*>(exact.data()),
        exact.size()*sizeof(exact[0]));
    material.append(reinterpret_cast<const char*>(control.data()),
        control.size()*sizeof(control[0]));
    const std::string hex=leo::adaptive::sha256(material);
    std::array<std::uint8_t,32> digest{};
    auto nibble=[](char value) -> std::uint8_t {
        return static_cast<std::uint8_t>(value<='9' ? value-'0' : value-'a'+10);
    };
    for (std::size_t i=0;i<digest.size();++i)
        digest[i]=static_cast<std::uint8_t>((nibble(hex[2U*i])<<4U)|nibble(hex[2U*i+1U]));
    return digest;
}

bool compatible_detector_capabilities(const leo_native_glrt_capabilities& a,
                                      const leo_native_glrt_capabilities& b) {
    return a.abi_version==b.abi_version && a.receiver_count==b.receiver_count &&
        a.probe_ms==b.probe_ms && a.process_serialized==b.process_serialized &&
        a.candidate_cfo_refinement_state_available==
            b.candidate_cfo_refinement_state_available &&
        a.fractional_epoch_mode_available==b.fractional_epoch_mode_available &&
        a.fractional_epoch_server_parity_qualified==
            b.fractional_epoch_server_parity_qualified;
}
int cancel_source(void* context) {
    return leo_local_source_cancel(static_cast<leo_local_source*>(context));
}
int source_counter(void* context,std::uint64_t* out) {
    return leo_local_source_snapshot(static_cast<leo_local_source*>(context),out);
}

struct PrimeDeadline {
    leo_local_source* source;
    std::mutex mutex;
    std::condition_variable changed;
    bool finished{};
    std::thread worker;
    PrimeDeadline(leo_local_source* value,std::uint64_t deadline,std::uint64_t now)
        : source(value),worker([this,deadline,now] {
            std::unique_lock<std::mutex> lock(mutex);
            if (!changed.wait_for(lock,std::chrono::nanoseconds(deadline-now),
                    [this] { return finished; }))
                (void)leo_local_source_cancel(source);
        }) {}
    ~PrimeDeadline() {
        {
            std::lock_guard<std::mutex> lock(mutex); finished=true;
        }
        changed.notify_one(); if (worker.joinable()) worker.join();
    }
};

struct CounterContext { leo_local_source* source{}; Analysis* analysis{}; };
int timed_snapshot(void* context,std::uint64_t* out) {
    auto& value=*static_cast<CounterContext*>(context);
    timing::PosixClock clock{value.source,source_counter,true}; timing::Bracket bracket;
    const auto status=timing::read_bracket(clock.port(),bracket);
    if (status!=timing::Status::ok) return -EIO;
    if (value.analysis->observe(bracket)!=timing::Status::ok) return -ETIME;
    *out=bracket.counter; return 0;
}
void event_sink(void* context,const leo_scanner_event* event) {
    if (context && event) static_cast<Analysis*>(context)->event(*event);
}

int run_with_providers(int argc,char** argv,const leo_local_provider_ops* source_provider,
                       const leo_local_radio_prepare_ops* radio_provider,
                       const SupportDerivationPort* support_profile) {
    const bool profiled=support_profile!=nullptr;
    if (profiled && !valid_support_port(*support_profile)) return 2;
    if (argc==1) {
        std::cout<<"{\"schema\":\""<<(profiled ?
            "leo-native-live-profiled-capabilities/v1" :
            "leo-native-live-capabilities/v4")<<"\",\"capture\":false,"
            "\"requires_explicit_capture_flag\":true,\"maximum_duration_ms\":1800000,"
            "\"source\":\"local-pluto\",\"sample_rate_hz\":2500000,"
            "\"receiver_count\":2,\"supported_history_seconds\":[10,600],"
            "\"default_cpu_workers\":2,\"default_detector_workers\":1,"
            "\"default_analysis_workers\":1,\"maximum_workers_per_pool\":4,"
            "\"search_publication_policy\":\"pin-started-snapshot\","
            "\"analysis_scopes\":[\"reduced-history-development\","
            "\"full-history-development\"]";
        if (profiled) std::cout<<",\"support_profile_name\":\""
            <<support_profile->profile_name<<"\",\"support_profile_manifest_digest\":\""
            <<support_profile->profile_manifest_digest
            <<"\",\"strict_pipeline_parity_qualified\":false";
        std::cout<<"}\n";
        return 0;
    }
    Parsed parsed; if (!parse(argc,argv,parsed)) return 2;
    const application::ExecutionBudget execution_budget{parsed.cpu_workers,
        parsed.detector_workers,parsed.analysis_workers};
    try { execution_budget.validate(application::ExecutionMode::live); }
    catch (...) { return 2; }
    if (!source_provider || !radio_provider) return 3;
    std::uint64_t started=0; if (monotonic_ns(started)) return 3;
    const auto duration_ns=static_cast<std::uint64_t>(parsed.duration_ms)*1000000ULL;
    if (started>UINT64_MAX-duration_ns) return 3;
    const auto deadline=started+duration_ns;
    constexpr std::uint32_t rate=2500000;
    const auto template_count=(rate+375U)/750U;
    const auto exact=read_exact<leo_native_glrt_complex>(parsed.exact,template_count);
    const auto control=read_exact<leo_native_glrt_complex>(parsed.control,template_count);
    auto catalogue=read_tles(parsed.tles);
    constexpr std::uint32_t detector_mode=
        LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH;
    std::vector<DetectorOwner> detector_contexts;
    detector_contexts.reserve(parsed.detector_workers);
    int status=0;
    for (std::uint32_t i=0;i<parsed.detector_workers;++i) {
        leo_native_glrt* context=nullptr;
        status=leo_native_glrt_create_with_mode(&context,rate,exact.data(),control.data(),
            template_count,detector_mode);
        if (status) return 4;
        detector_contexts.emplace_back(context);
    }
    leo_native_glrt_capabilities common_capabilities{};
    for (std::size_t i=0;i<detector_contexts.size();++i) {
        leo_native_glrt_capabilities capabilities{};
        if (detector_capabilities(detector_contexts[i].get(),&capabilities) ||
            capabilities.abi_version!=LEO_NATIVE_GLRT_ABI_VERSION ||
            capabilities.receiver_count!=2U || capabilities.probe_ms!=20U ||
            !capabilities.fractional_epoch_mode_available ||
            (detector_contexts.size()>1U && capabilities.process_serialized) ||
            (i && !compatible_detector_capabilities(common_capabilities,capabilities)))
            return 4;
        if (!i) common_capabilities=capabilities;
    }
    const auto attestation=detector_binding_digest(parsed.analysis_digest,exact,control,
        rate,detector_mode);
    std::vector<leo_scanner_detector_binding> detector_bindings(
        detector_contexts.size());
    for (std::size_t i=0;i<detector_bindings.size();++i) {
        detector_bindings[i].abi_version=LEO_SCANNER_EXECUTION_ABI_VERSION;
        detector_bindings[i].ops={detector_contexts[i].get(),detector_analyze,
            detector_capabilities};
        std::copy(attestation.begin(),attestation.end(),
            detector_bindings[i].configuration_digest);
    }
    const leo_scanner_execution_options scanner_execution{
        LEO_SCANNER_EXECUTION_ABI_VERSION,parsed.detector_workers,
        detector_bindings.data()};
    std::uint64_t setup_now=0;
    if (monotonic_ns(setup_now) || setup_now>=deadline) return 4;

    leo_local_config local{}; local.sample_rate_hz=rate; local.analog_bandwidth_hz=rate;
    local.samples_per_block=rate*parsed.block_ms/1000; local.receiver_count=2;
    local.kernel_buffer_count=LEO_LOCAL_RADIO_KERNEL_BUFFERS;
    local.profile_count=static_cast<std::uint32_t>(parsed.targets.size());
    leo_local_radio_prepare_config prepare{}; prepare.abi_version=LEO_LOCAL_RADIO_PREPARE_ABI_VERSION;
    prepare.sample_rate_hz=rate; prepare.analog_bandwidth_hz=rate; prepare.receiver_count=2;
    prepare.manual_gain_millidb=40000; prepare.target_count=local.profile_count;
    for (std::size_t i=0;i<parsed.targets.size();++i) {
        local.profiles[i].profile=parsed.targets[i].profile;
        local.profiles[i].frequency_hz=parsed.targets[i].frequency_hz;
        prepare.targets[i].profile=parsed.targets[i].profile;
        prepare.targets[i].frequency_hz=parsed.targets[i].frequency_hz;
    }
    leo_local_owner* owner=nullptr; leo_local_radio_preparation* preparation=nullptr;
    leo_local_source* source=nullptr; int close_status=0,deactivate_status=0,restore_status=0,
        owner_status=0,detector_status=0;
    bool cleaned=false;
    auto cleanup=[&] {
        if (cleaned) return;
        cleaned=true;
        if (source) {
            leo_local_owner* returned=nullptr;
            close_status=leo_local_source_close_preserve_owner(source,&returned);
            source=nullptr; owner=returned;
        }
        if (owner && leo_local_owner_is_active(owner)) {
            leo_local_restore_receipt receipt{};
            deactivate_status=leo_local_owner_deactivate(owner,0,&receipt);
        }
        if (preparation) {
            leo_local_radio_restore_receipt receipt{};
            restore_status=leo_local_radio_restore(&preparation,owner,&receipt);
            if (restore_status && preparation)
                restore_status=leo_local_radio_restore(&preparation,owner,&receipt);
        }
        if (owner) {
            leo_local_restore_receipt receipt{};
            owner_status=leo_local_owner_release(owner,0,&receipt); owner=nullptr;
        }
        for (auto& context:detector_contexts) if (context) {
            const int destroyed=leo_native_glrt_destroy(context.release());
            if (!detector_status && destroyed) detector_status=destroyed;
        }
    };
    ScopeExit base_cleanup(cleanup);
    if ((status=leo_local_radio_preflight_inactive(radio_provider)) ||
        (status=leo_local_owner_acquire(&local,source_provider,&owner))) {
        cleanup(); return 5;
    }
    leo_local_radio_prepare_receipt prepared{};
    status=leo_local_radio_prepare_owned(&prepare,radio_provider,owner,
        &preparation,&prepared);
    if (status) { cleanup(); return 5; }
    for (std::size_t i=0;i<parsed.targets.size();++i) {
        local.profiles[i].crc32=prepared.targets[i].profile_crc32;
    }
    if ((status=leo_local_source_open_owned(&local,source_provider,owner,&source))) {
        cleanup(); return 5;
    }
    std::uint64_t now=0; if (monotonic_ns(now) || now>=deadline) status=-ETIMEDOUT;
    leo_local_prime_receipt prime{};
    if (!status) {
        PrimeDeadline guard(source,deadline,now);
        status=leo_local_source_prime(source,&prime);
    }
    if (status) { cleanup(); return 6; }

    timing::PosixClock initial_clock{source,source_counter,true}; timing::Bracket initial;
    if (timing::read_bracket(initial_clock.port(),initial)!=timing::Status::ok) {
        cleanup(); return 7;
    }
    const auto bracket_width=initial.utc_after_ns-initial.utc_before_ns;
    const auto session_utc=initial.utc_before_ns+bracket_width/2;
    ingest::Authority authority{parsed.generation,rate,parsed.input_digest,parsed.analysis_digest,{}};
    for (std::size_t i=0;i<parsed.targets.size();++i) {
        const auto& target=parsed.targets[i];
        authority.targets.push_back({target.profile,prepared.targets[i].profile_crc32,target.channel,
            target.frequency_hz,target.actual_rf_hz,target.upper_edge});
    }
    const bool full_history=parsed.history_seconds==600;
    const std::uint32_t orbit_knots=full_history ? 96U : 32U;
    const double orbit_step=full_history ? 10.0 : 1.0;
    online::Config online;
    online.publication_search_policy=online::PublicationSearchPolicy::pin_started_snapshot;
    online.history_window_ns=static_cast<std::int64_t>(parsed.history_seconds)*1000000000LL;
    online.maximum_satellites=static_cast<std::uint32_t>(catalogue.size());
    online.maximum_knots=orbit_knots;
    online.maximum_search_points=parsed.search_budget;
    online.maximum_orbit_bytes=catalogue.size()*orbit_knots*sizeof(leo_orbit_state)*2U;
    online::SearchConfig search{}; search.origin_latitude_deg=parsed.latitude;
    search.origin_longitude_deg=parsed.longitude; search.score=leo_score_default_config();
    search.policy.radius_km=parsed.radius_km; search.policy.region_size_km=parsed.region_km;
    search.policy.level_count=1; search.policy.levels_km[0]=parsed.level_km;
    search.policy.budget_points=parsed.search_budget;
    AnalysisConfig analysis_config{authority,
        {rate,1'000'000'000,120'000'000'000ULL,10,100,1024},online,
        {parsed.session_id,parsed.input_digest,session_utc},std::move(catalogue),search,
        static_cast<std::uint64_t>(parsed.maximum_detector_latency_ms)*1000000ULL,
        static_cast<std::uint64_t>(parsed.publication_ms)*1000000ULL,parsed.search_slice,
        orbit_step,orbit_knots};
    analysis_config.analysis_workers=parsed.analysis_workers;
    if (profiled) analysis_config.support_derivation=*support_profile;
    std::unique_ptr<Analysis> analysis;
    try { analysis=std::make_unique<Analysis>(std::move(analysis_config)); }
    catch (...) { throw; }
    auto rf_before_analysis=[&] { analysis->detach_cancel(); cleanup(); };
    ScopeExit analysis_cleanup(rf_before_analysis);
    base_cleanup.dismiss();
    if (analysis->observe(initial)!=timing::Status::ok) return 7;
    analysis->set_cancel(source,cancel_source);

    leo_scanner_config scanner{}; scanner.abi_version=LEO_SCANNER_ABI_VERSION;
    scanner.session=prime.coherent_counter ? prime.coherent_counter : 1;
    scanner.generation=parsed.generation; scanner.seed=scanner.session^0x9e3779b97f4a7c15ULL;
    scanner.sample_rate_hz=rate; scanner.receiver_count=2; scanner.duration_ms=parsed.duration_ms;
    scanner.maximum_visits=parsed.maximum_visits; scanner.wall_deadline_monotonic_ns=deadline;
    scanner.dwell_ms=parsed.dwell_ms; scanner.transition_budget_ms=20;
    scanner.maximum_revisit_ms=3000; scanner.feedback_age_ms=1000;
    scanner.application_delay_ms=1000; scanner.decay_ms=3000; scanner.maximum_boost=3;
    scanner.detector_queue_capacity=4; scanner.active_threshold_dbfs=-38.0;
    scanner.target_count=static_cast<std::uint32_t>(parsed.targets.size());
    for (std::size_t i=0;i<parsed.targets.size();++i) {
        scanner.targets[i]={parsed.targets[i].profile,parsed.targets[i].frequency_hz,
            prepared.targets[i].profile_crc32,1};
    }
    CounterContext counter_context{source,analysis.get()};
    leo_scanner_counter_ops counter{&counter_context,timed_snapshot};
    leo_scanner_stats scanner_stats{};
    const int scanner_status=leo_scanner_run_timed_ex(&scanner,source,&counter,
        &scanner_execution,event_sink,analysis.get(),&scanner_stats);
    // Stop RF and restore the radio before waiting for orbit/search analysis.
    analysis_cleanup.run();
    Summary summary;
    bool analysis_failure=false;
    try { summary=analysis->finish_after_rf_stopped(); }
    catch (...) {
        if (!profiled) return 8;
        summary=analysis->progress();
        analysis_failure=true;
    }
    const bool lossless=scanner_stats.visits_incomplete==0 && scanner_stats.missing_samples==0 &&
        scanner_stats.detector_queue_drops==0 && scanner_stats.detector_failures==0 &&
        summary.scanner_queue_drops==0 && summary.detector_failures==0;
    const bool cleanup_ok=!close_status && !deactivate_status && !restore_status &&
        !owner_status && !detector_status;
    const bool support_qualified=!profiled ||
        (summary.accepted_candidates>0 && summary.support_profile_bound &&
         summary.support_profile.profile_name==support_profile->profile_name &&
         summary.support_profile.profile_manifest_digest==
             support_profile->profile_manifest_digest &&
         summary.session.profile_prepared==summary.accepted_candidates &&
         summary.session.support_derived==summary.accepted_candidates &&
         summary.session.support_derivation_count==summary.accepted_candidates &&
         !summary.session.support_invalid && !summary.session.support_unavailable &&
         !summary.session.support_unhealthy &&
         !summary.session.discarded_after_support_failure &&
         !summary.session.rejected_after_support_failure);
    const bool capture_integrity_qualified=!analysis_failure &&
        !scanner_status && !scanner_stats.stop_status &&
        summary.timing_qualified && lossless && cleanup_ok &&
        summary.session.queue_dropped==0 && summary.session.rejected==0 &&
        summary.session.history_capacity_evictions==0 &&
        summary.publication_failures==0 && summary.search_failures==0 && support_qualified;
    const auto selected=summary.last_search.has_incumbent ?
        offset_coordinate(parsed.latitude,parsed.longitude,
            summary.last_search.incumbent.east_km,summary.last_search.incumbent.north_km) :
        std::pair<double,double>{0,0};
    std::cout<<std::setprecision(17)<<"{\"schema\":\""<<(profiled ?
        "leo-native-live-profiled-summary/v1" : "leo-native-live-summary/v4")<<"\","
        "\"search_publication_policy\":\"pin-started-snapshot\","
        "\"cpu_workers\":"<<parsed.cpu_workers
        <<",\"detector_workers\":"<<parsed.detector_workers
        <<",\"analysis_workers\":"<<parsed.analysis_workers<<","
        "\"analysis_scope\":\""<<(full_history ? "full-history-development" :
            "reduced-history-development")<<"\",\"history_seconds\":"
        <<parsed.history_seconds<<"," 
        "\"scanner_status\":"<<scanner_status<<",\"scanner_stop_status\":"
        <<scanner_stats.stop_status<<",\"visits\":"<<scanner_stats.visits_started
        <<",\"intact\":"<<scanner_stats.visits_intact
        <<",\"detector_queue_drops\":"<<scanner_stats.detector_queue_drops
        <<",\"detector_failures\":"<<scanner_stats.detector_failures
        <<",\"missing_samples\":"<<scanner_stats.missing_samples
        <<",\"incomplete_visits\":"<<scanner_stats.visits_incomplete
        <<",\"accepted_candidates\":"<<summary.accepted_candidates
        <<",\"application_queue_drops\":"<<summary.session.queue_dropped
        <<",\"application_rejected\":"<<summary.session.rejected
        <<",\"history_capacity_evictions\":"
        <<summary.session.history_capacity_evictions
        <<",\"scanner_drop_events\":"<<summary.scanner_queue_drops
        <<",\"detector_failure_events\":"<<summary.detector_failures
        <<",\"detector_latency_violations\":"<<summary.detector_latency_violations
        <<",\"invalid_candidate_events\":"<<summary.invalid_candidate_events
        <<",\"publications\":"<<summary.publications
        <<",\"publications_with_tracks\":"<<summary.publications_with_tracks
        <<",\"publication_empty\":"<<summary.publication_empty
        <<",\"publication_failures\":"<<summary.publication_failures
        <<",\"publication_deferrals\":"<<summary.publication_deferrals
        <<",\"watermark_deferrals\":"<<summary.watermark_deferrals
        <<",\"publication_compute_count\":"<<summary.publication_compute_count
        <<",\"publication_compute_total_ns\":"<<summary.publication_compute_total_ns
        <<",\"publication_compute_max_ns\":"<<summary.publication_compute_max_ns
        <<",\"publication_cadence_requests\":"<<summary.publication_cadence_requests
        <<",\"publication_cadence_serviced\":"<<summary.publication_cadence_serviced
        <<",\"publication_cadence_misses\":"<<summary.publication_cadence_misses
        <<",\"publication_cadence_pending\":"
        <<(summary.publication_cadence_pending?"true":"false")
        <<",\"latest_source_progress_utc_before_ns\":"
        <<summary.latest_measured_source_progress_utc_before_ns
        <<",\"latest_source_progress_utc_after_ns\":"
        <<summary.latest_measured_source_progress_utc_after_ns
        <<",\"latest_causal_frontier_utc_ns\":"<<summary.latest_causal_frontier_utc_ns
        <<",\"last_snapshot_watermark_utc_ns\":"<<summary.last_snapshot_watermark_utc_ns
        <<",\"publication_lag_current_ns\":"<<summary.publication_lag_current_ns
        <<",\"publication_lag_max_ns\":"<<summary.publication_lag_max_ns
        <<",\"snapshot_source_age_count\":"<<summary.snapshot_source_age_count
        <<",\"snapshot_source_age_lower_current_ns\":"
        <<summary.snapshot_source_age_lower_current_ns
        <<",\"snapshot_source_age_upper_current_ns\":"
        <<summary.snapshot_source_age_upper_current_ns
        <<",\"snapshot_source_age_lower_max_ns\":"
        <<summary.snapshot_source_age_lower_max_ns
        <<",\"snapshot_source_age_upper_max_ns\":"
        <<summary.snapshot_source_age_upper_max_ns
        <<",\"result_source_age_count\":"<<summary.result_source_age_count
        <<",\"result_source_age_lower_current_ns\":"
        <<summary.result_source_age_lower_current_ns
        <<",\"result_source_age_upper_current_ns\":"
        <<summary.result_source_age_upper_current_ns
        <<",\"result_source_age_lower_max_ns\":"<<summary.result_source_age_lower_max_ns
        <<",\"result_source_age_upper_max_ns\":"<<summary.result_source_age_upper_max_ns
        <<",\"snapshot_result_duration_count\":"<<summary.snapshot_result_duration_count
        <<",\"snapshot_result_duration_current_ns\":"
        <<summary.snapshot_result_duration_current_ns
        <<",\"snapshot_result_duration_max_ns\":"<<summary.snapshot_result_duration_max_ns
        <<",\"orbit_builds\":"<<summary.orbit_builds
        <<",\"searches_started\":"<<summary.searches_started
        <<",\"searches_complete\":"<<summary.searches_complete
        <<",\"searches_unconverged\":"<<summary.searches_unconverged
        <<",\"searches_stale\":"<<summary.searches_stale
        <<",\"search_pending\":"<<(summary.search_pending?"true":"false")
        <<",\"search_failures\":"<<summary.search_failures
        <<",\"snapshot_generation\":"<<summary.snapshot_generation
        <<",\"orbit_generation\":"<<summary.orbit_generation
        <<",\"last_search_state\":"<<static_cast<unsigned>(summary.last_search.state)
        <<",\"last_search_snapshot_generation\":"<<summary.last_search.snapshot_generation
        <<",\"last_search_orbit_generation\":"<<summary.last_search.orbit_generation
        <<",\"last_search_evaluated_points\":"<<summary.last_search.evaluated_points
        <<",\"last_search_required_points\":"<<summary.last_search.required_points
        <<",\"last_search_deferred_cells\":"<<summary.last_search.deferred_cells
        <<",\"last_search_has_incumbent\":"
        <<(summary.last_search.has_incumbent?"true":"false")
        <<",\"selected\":";
    if (summary.last_search.has_incumbent) {
        std::cout<<"{\"latitude_deg\":"<<selected.first
            <<",\"longitude_deg\":"<<selected.second
            <<",\"east_km\":"<<summary.last_search.incumbent.east_km
            <<",\"north_km\":"<<summary.last_search.incumbent.north_km
            <<",\"weighted_mse_hz2\":"<<summary.last_search.incumbent.weighted_mse_hz2
            <<",\"residual_rmse_hz\":"<<summary.last_search.incumbent_residual_rmse_hz
            <<",\"matched_tracks\":"<<summary.last_search.incumbent_matched_tracks
            <<",\"unmatched_tracks\":"<<summary.last_search.incumbent_unmatched_tracks
            <<"}";
    } else std::cout<<"null";
    if (profiled) {
        std::cout<<",\"support_profile_name\":\""
            <<summary.support_profile.profile_name
            <<"\",\"support_profile_manifest_digest\":\""
            <<summary.support_profile.profile_manifest_digest
            <<"\",\"profile_prepared\":"<<summary.session.profile_prepared
            <<",\"support_derived\":"<<summary.session.support_derived
            <<",\"support_derivation_count\":"
            <<summary.session.support_derivation_count
            <<",\"support_derivation_total_ns\":"
            <<summary.session.support_derivation_total_ns
            <<",\"support_derivation_max_ns\":"
            <<summary.session.support_derivation_max_ns
            <<",\"support_invalid\":"<<summary.session.support_invalid
            <<",\"support_unavailable\":"<<summary.session.support_unavailable
            <<",\"support_unhealthy\":"
            <<(summary.session.support_unhealthy?"true":"false")
            <<",\"discarded_after_support_failure\":"
            <<summary.session.discarded_after_support_failure
            <<",\"rejected_after_support_failure\":"
            <<summary.session.rejected_after_support_failure
            <<",\"support_profile_qualified\":"
            <<(support_qualified?"true":"false")
            <<",\"strict_pipeline_parity_qualified\":false";
    }
    std::cout
        <<",\"timing_qualified\":"<<(summary.timing_qualified?"true":"false")
        <<",\"lossless\":"<<(lossless?"true":"false")
        <<",\"capture_integrity_qualified\":"
        <<(capture_integrity_qualified?"true":"false")
        <<",\"reduced_history_qualified\":"
        <<(!full_history && capture_integrity_qualified?"true":"false")
        <<",\"full_history_development_executed\":"
        <<(full_history?"true":"false")
        <<",\"full_standard_qualified\":false,\"fractional_server_parity_qualified\":false"
        <<",\"cleanup\":{\"source_close\":"<<close_status
        <<",\"owner_deactivate\":"<<deactivate_status<<",\"radio_restore\":"
        <<restore_status<<",\"owner_release\":"<<owner_status
        <<",\"detector_destroy\":"<<detector_status<<"}}\n";
    return capture_integrity_qualified ? 0 : 8;
}
} // namespace

namespace leo::adaptive::application::live {
int run_cli_with_providers(int argc,char** argv,const leo_local_provider_ops* source_provider,
                           const leo_local_radio_prepare_ops* radio_provider) {
    return run_with_providers(argc,argv,source_provider,radio_provider,nullptr);
}
int run_cli_with_providers_and_support(int argc,char** argv,
        const leo_local_provider_ops* source_provider,
        const leo_local_radio_prepare_ops* radio_provider,
        const SupportDerivationPort& support_profile) {
    return run_with_providers(argc,argv,source_provider,radio_provider,&support_profile);
}
}

#ifndef LEO_LIVE_NO_MAIN
int main(int argc,char** argv) {
    try { return leo::adaptive::application::live::run_cli_with_providers(argc,argv,
        leo_local_iio_provider(),leo_local_iio_radio_prepare_provider()); }
    catch (const std::exception& error) { std::cerr<<error.what()<<'\n'; return 9; }
}
#endif
#endif
