#pragma once

#include <cstddef>
#include <cstdint>
#include <condition_variable>
#include <exception>
#include <functional>
#include <mutex>
#include <thread>
#include <vector>

namespace leo { namespace adaptive {

// Internal native contract, not a replacement for a published persisted ABI.
struct Visit {
    uint64_t generation, visit, first, end;
    uint32_t rate, receivers;
    double actual_rf_hz;
};
struct Window {
    Visit visit;
    uint64_t first;
    uint32_t index, samples;
    // Borrowed only during the sink invocation; sample, receiver, I/Q order.
    const int16_t* iq;
};
struct WindowStats { uint64_t emitted=0, missing=0, discontinuities=0; };

class WindowAssembler {
public:
    using Sink = std::function<void(const Window&)>;
    WindowAssembler(uint32_t maximum_rate, uint32_t maximum_receivers, Sink sink);
    void begin(const Visit& visit);
    void push(uint64_t first, const int16_t* samples, size_t sample_times);
    void finish();
    WindowStats stats() const { return stats_; }
private:
    void advance();
    uint32_t maximum_rate_, maximum_receivers_, width_=0, stride_=0, index_=0;
    Visit visit_{};
    uint64_t expected_=0, next_=0;
    size_t filled_=0;
    bool active_=false;
    std::vector<int16_t> buffer_;
    Sink sink_;
    WindowStats stats_;
};

struct Support {
    int64_t first, end;
    double center, moment2, moment3;
    uint32_t symbols;
};
Support fractional_support(uint32_t rate, uint32_t probe_samples,
                           int64_t epoch, double fractional_offset);
// Integer subtraction precedes floating-point conversion, including >2^53 counters.
int64_t support_utc_ns(uint64_t anchor_counter, int64_t anchor_utc_ns,
                       uint64_t window_counter, double local_sample, uint32_t rate);

struct Job {
    uint64_t id=0;
    void (*run)(void*, size_t)=nullptr;
    void* context=nullptr;
};
struct ExecutorStats {
    uint64_t accepted=0, completed=0, failed=0, rejected=0, cancelled=0;
    size_t queued=0, running=0, high_water=0;
};

// One bounded executor per explicitly reserved lane. Caller configures a total
// worker budget (e.g. one detector plus one background worker on PLUTO+).
// Jobs cannot spawn another pool here; input/context lifetime extends to drain.
class Executor {
public:
    Executor(size_t workers, size_t queue_capacity);
    ~Executor();
    Executor(const Executor&)=delete;
    Executor& operator=(const Executor&)=delete;
    bool submit(Job job);
    void drain();
    void stop(bool cancel_pending=false);
    ExecutorStats stats() const;
    void rethrow_first_failure() const;
private:
    void work(size_t worker);
    mutable std::mutex mutex_;
    std::condition_variable ready_, idle_;
    std::vector<Job> ring_;
    std::vector<std::thread> workers_;
    size_t head_=0, tail_=0;
    bool stopping_=false;
    ExecutorStats stats_;
    std::exception_ptr failure_;
};

} }
