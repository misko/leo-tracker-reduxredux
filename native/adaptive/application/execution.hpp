#pragma once

#include "../runtime/runtime.hpp"
#include "../tracking/tracking.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <exception>
#include <memory>
#include <stdexcept>

namespace leo::adaptive::application {

enum class ExecutionMode {
    live,
    replay,
};

struct ExecutionBudget {
    std::uint32_t total_cpu_lanes{2};
    std::uint32_t detector_workers{1};
    std::uint32_t analysis_workers{1};

    bool valid(ExecutionMode mode) const noexcept {
        if (total_cpu_lanes < 1 || total_cpu_lanes > 4 || analysis_workers < 1 ||
            analysis_workers > 4 || detector_workers > 4) {
            return false;
        }
        if (mode == ExecutionMode::live && detector_workers < 1) return false;
        if (mode != ExecutionMode::live && mode != ExecutionMode::replay) return false;
        return detector_workers + analysis_workers <= total_cpu_lanes;
    }

    void validate(ExecutionMode mode) const {
        if (!valid(mode)) throw std::invalid_argument("invalid application execution budget");
    }
};

/* Owns the workers behind one borrowed synchronous tracking port. Keep this
 * object alive until every coordinator/session holding port() has been
 * destroyed. One analysis worker is the serial path and allocates no executor.
 *
 * A failed callback drains all jobs already accepted in its bounded chunk,
 * discards the failed executor, and rethrows. A later dispatch creates a fresh
 * executor. Jobs in later chunks were never accepted and are not invoked.
 */
class TrackingExecution {
public:
    explicit TrackingExecution(std::uint32_t analysis_workers)
        : workers_(analysis_workers) {
        if (workers_ < 1 || workers_ > 4) {
            throw std::invalid_argument("tracking workers must be in [1,4]");
        }
        if (workers_ > 1) executor_ = make_executor();
    }

    ~TrackingExecution() = default;
    TrackingExecution(const TrackingExecution&) = delete;
    TrackingExecution& operator=(const TrackingExecution&) = delete;
    TrackingExecution(TrackingExecution&&) = delete;
    TrackingExecution& operator=(TrackingExecution&&) = delete;

    std::uint32_t workers() const noexcept { return workers_; }

    tracking::LaneExecution port() noexcept {
        if (workers_ == 1) return {};
        return {this, &TrackingExecution::run};
    }

private:
    struct Task {
        void* context{};
        void (*run)(void*, std::size_t){};
        std::size_t index{};
    };

    class DispatchGuard {
    public:
        explicit DispatchGuard(std::atomic_flag& active) : active_(active) {
            if (active_.test_and_set(std::memory_order_acquire)) {
                throw std::logic_error("overlapping tracking dispatch");
            }
            owns_ = true;
        }
        ~DispatchGuard() {
            if (owns_) active_.clear(std::memory_order_release);
        }
        DispatchGuard(const DispatchGuard&) = delete;
        DispatchGuard& operator=(const DispatchGuard&) = delete;
    private:
        std::atomic_flag& active_;
        bool owns_{};
    };

    std::unique_ptr<Executor> make_executor() const {
        return std::make_unique<Executor>(workers_, workers_);
    }

    static void invoke(void* opaque, std::size_t) {
        auto& task = *static_cast<Task*>(opaque);
        task.run(task.context, task.index);
    }

    static void run(void* opaque, std::size_t count, void* task_context,
                    void (*task)(void*, std::size_t)) {
        static_cast<TrackingExecution*>(opaque)->dispatch(count, task_context, task);
    }

    void dispatch(std::size_t count, void* task_context,
                  void (*task)(void*, std::size_t)) {
        if (!task) throw std::invalid_argument("tracking task is null");
        DispatchGuard guard(active_);
        if (!executor_) executor_ = make_executor();
        std::array<Task, 4> tasks{};
        try {
            for (std::size_t first = 0; first < count;) {
                const std::size_t chunk = std::min<std::size_t>(workers_, count - first);
                for (std::size_t offset = 0; offset < chunk; ++offset) {
                    tasks[offset] = {task_context, task, first + offset};
                    if (!executor_->submit(Job{first + offset, &TrackingExecution::invoke,
                                                &tasks[offset]})) {
                        executor_->drain();
                        executor_->rethrow_first_failure();
                        throw std::runtime_error("tracking executor rejected a bounded job");
                    }
                }
                executor_->drain();
                executor_->rethrow_first_failure();
                first += chunk;
            }
        } catch (...) {
            const std::exception_ptr failure = std::current_exception();
            executor_->drain();
            executor_.reset();
            std::rethrow_exception(failure);
        }
    }

    const std::uint32_t workers_;
    std::unique_ptr<Executor> executor_;
    std::atomic_flag active_ = ATOMIC_FLAG_INIT;
};

}  // namespace leo::adaptive::application
