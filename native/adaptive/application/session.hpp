#pragma once
#include "../ingest/ingest.hpp"
#include "../online/online.hpp"
#include <deque>
#include <mutex>
#include <optional>

namespace leo::adaptive::application {
struct Stats {
    std::uint64_t projected{}, nonpassing{}, invalid{}, timing_unavailable{},
        queue_dropped{}, consumed{}, rejected{}, profile_prepared{},
        support_derived{}, support_invalid{}, support_unavailable{},
        discarded_after_support_failure{}, rejected_after_support_failure{},
        support_derivation_count{}, support_derivation_total_ns{},
        support_derivation_max_ns{};
    std::size_t queued{}, high_water{};
    std::uint64_t history_capacity_evictions{};
    bool support_derivation_inflight{}, support_unhealthy{};
};
struct AcceptReceipt {
    ingest::Status projection;
    bool queued{};
    // True only when a validated value-owned projection was actually queued;
    // numeric support and the Observation are produced later by the owner.
    bool deferred{};
};
enum class ConsumeStatus {
    empty,
    ok,
    support_invalid,
    support_unavailable,
    coordinator_rejected,
    unhealthy,
    busy,
};
struct ConsumeReceipt {
    std::size_t dequeued{}, ingested{};
    ConsumeStatus status{ConsumeStatus::empty};
};
// One invocation has immutable stream/input/analysis authority. Acquisition
// calls observe/accept; a separate single analysis owner calls all other work.
// No hidden pool: replay can use the same owner synchronously; PLUTO+ can place
// it on the background lane. Construct a new Session for a new source generation.
class Session {
public:
    Session(ingest::Authority, timing::Config, online::Config,
            online::SessionAuthority, std::size_t queue_capacity);
    // Opt-in session-bound support authority. Binding views are copied during
    // construction; context/callback remain borrowed until Session destruction
    // after producer calls stop. The existing constructor stays portable.
    Session(ingest::Authority, timing::Config, online::Config,
            online::SessionAuthority, std::size_t queue_capacity,
            const SupportDerivationPort&);
    // Optional bounded historical timing authority. It composes with the
    // support-authority port, while the default constructors retain measured
    // Timebase projection semantics.
    Session(ingest::Authority, timing::Config, online::Config,
            online::SessionAuthority, std::size_t queue_capacity,
            const ingest::HistoricalTimingProfile&);
    Session(ingest::Authority, timing::Config, online::Config,
            online::SessionAuthority, std::size_t queue_capacity,
            const SupportDerivationPort&, const ingest::HistoricalTimingProfile&);
    timing::Status observe(const timing::Bracket&);
    AcceptReceipt accept(const leo_scanner_event&);
    ConsumeReceipt consume_reported(std::size_t maximum);
    // Compatibility wrapper. A deferred support failure throws so legacy
    // callers cannot silently discard a failed profiled candidate.
    std::size_t consume(std::size_t maximum);
    // Analysis owner supplies measured source progress during quiet periods;
    // this expires old evidence even when no candidate arrives. Drain the inbox
    // first; pending accepted evidence rejects advancement. The caller must
    // separately account for detector work that has not delivered results yet.
    online::Status advance_watermark(std::int64_t);
    // Analysis-owner query; consuming candidates may advance beyond the latest
    // conservative quiet frontier, which must never move this clock backward.
    std::int64_t watermark() const;
    online::Status publish(std::shared_ptr<const online::Snapshot>*);
    // Analysis-owner-only view; no new publication or retained history is made.
    std::shared_ptr<const online::Snapshot> current_snapshot() const;
    online::Status replace_orbit(const online::OrbitBuild&);
    online::Status begin_search(std::uint64_t, const online::SearchConfig&,
                                online::SearchResult*);
    online::SearchResult resume_search(std::uint32_t maximum_points);
    online::SearchResult cancel_search();
    Stats stats() const;
    // Analysis-owner-only query. Unlike stats(), this is not producer-safe;
    // scoring mutates these counters while resume_search executes.
    online::ExactScoreCacheStats exact_score_cache_stats() const;
    // This session-level authority is deliberately not repeated in Snapshot.
    // A publisher claiming an opt-in support profile must persist/report this
    // binding alongside the snapshot it obtained from this Session.
    const SupportProfileBinding* support_profile_binding() const noexcept;
    const ingest::HistoricalTimingProfile* historical_timing_profile() const noexcept;
private:
    Session(ingest::Authority, timing::Config, online::Config,
            online::SessionAuthority, std::size_t queue_capacity,
            const SupportDerivationPort*, const ingest::HistoricalTimingProfile*);
    struct Pending {
        Observation observation{};
        ingest::PreparedProjection prepared{};
        std::int64_t watermark{};
        bool deferred{};
    };
    const ingest::Authority authority_;
    timing::Timebase timing_;
    online::Coordinator coordinator_;
    const std::size_t capacity_;
    SupportProfileBinding support_binding_;
    void* support_context_{};
    SupportDeriveFunction support_derive_{};
    std::optional<ingest::HistoricalTimingProfile> historical_timing_;
    mutable std::mutex mutex_;
    std::deque<Pending> pending_;
    Stats stats_;
    bool support_derivation_inflight_{}, support_unhealthy_{};
};
}
