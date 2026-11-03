#include "execution.hpp"

#include <array>
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <stdexcept>
#include <thread>

using leo::adaptive::application::ExecutionBudget;
using leo::adaptive::application::ExecutionMode;
using leo::adaptive::application::TrackingExecution;

namespace {

template <typename Function>
bool throws_invalid(Function&& function) {
    try {
        function();
    } catch (const std::invalid_argument&) {
        return true;
    }
    return false;
}

void test_budgets() {
    const ExecutionBudget defaults{};
    assert(defaults.valid(ExecutionMode::live));
    assert(defaults.valid(ExecutionMode::replay));
    defaults.validate(ExecutionMode::live);

    for (std::uint32_t total = 0; total <= 5; ++total) {
        for (std::uint32_t detector = 0; detector <= 5; ++detector) {
            for (std::uint32_t analysis = 0; analysis <= 5; ++analysis) {
                const ExecutionBudget value{total, detector, analysis};
                const bool common = total >= 1 && total <= 4 && analysis >= 1 &&
                    analysis <= 4 && detector <= 4 && detector + analysis <= total;
                assert(value.valid(ExecutionMode::live) == (common && detector >= 1));
                assert(value.valid(ExecutionMode::replay) == common);
            }
        }
    }
    const auto unknown = static_cast<ExecutionMode>(99);
    assert(!defaults.valid(unknown));
    assert(throws_invalid([&] { defaults.validate(unknown); }));
    assert((ExecutionBudget{1, 0, 1}.valid(ExecutionMode::replay)));
    assert((!ExecutionBudget{1, 0, 1}.valid(ExecutionMode::live)));
    assert(throws_invalid([] { ExecutionBudget{4, 1, 4}.validate(ExecutionMode::live); }));
}

void test_serial_default() {
    TrackingExecution execution(1);
    assert(execution.workers() == 1);
    assert(execution.port().run == nullptr);
    assert(throws_invalid([] { TrackingExecution invalid(0); }));
    assert(throws_invalid([] { TrackingExecution invalid(5); }));
}

void test_parallel_exact_once() {
    TrackingExecution execution(4);
    auto port = execution.port();
    assert(port.run != nullptr && port.context == &execution);
    std::array<std::atomic<unsigned>, 19> calls{};
    port.run(port.context, calls.size(), &calls,
        [](void* opaque, std::size_t index) {
            auto& values = *static_cast<decltype(calls)*>(opaque);
            ++values[index];
        });
    for (const auto& count : calls) assert(count.load() == 1);
}

void test_exception_drain_and_recovery() {
    struct State {
        std::array<std::atomic<unsigned>, 7> calls{};
        std::size_t failing{1};
    } state;
    TrackingExecution execution(3);
    auto port = execution.port();
    bool caught = false;
    try {
        port.run(port.context, state.calls.size(), &state,
            [](void* opaque, std::size_t index) {
                auto& value = *static_cast<State*>(opaque);
                ++value.calls[index];
                if (index == value.failing) throw std::runtime_error("injected callback failure");
            });
    } catch (const std::runtime_error&) {
        caught = true;
    }
    assert(caught);
    for (std::size_t index = 0; index < state.calls.size(); ++index) {
        assert(state.calls[index].load() == (index < 3 ? 1U : 0U));
        state.calls[index] = 0;
    }

    state.failing = state.calls.size();
    port.run(port.context, state.calls.size(), &state,
        [](void* opaque, std::size_t index) {
            auto& value = *static_cast<State*>(opaque);
            ++value.calls[index];
        });
    for (const auto& count : state.calls) assert(count.load() == 1);
}

void test_overlap_rejected() {
    struct Blocking {
        std::mutex mutex;
        std::condition_variable ready;
        std::condition_variable release;
        std::size_t started{};
        bool go{};
    } blocking;
    TrackingExecution execution(2);
    auto port = execution.port();
    std::thread first([&] {
        port.run(port.context, 2, &blocking,
            [](void* opaque, std::size_t) {
                auto& state = *static_cast<Blocking*>(opaque);
                std::unique_lock<std::mutex> lock(state.mutex);
                ++state.started;
                state.ready.notify_one();
                state.release.wait(lock, [&] { return state.go; });
            });
    });
    {
        std::unique_lock<std::mutex> lock(blocking.mutex);
        blocking.ready.wait(lock, [&] { return blocking.started == 2; });
    }
    bool rejected = false;
    try {
        port.run(port.context, 0, nullptr, [](void*, std::size_t) {});
    } catch (const std::logic_error&) {
        rejected = true;
    }
    assert(rejected);
    {
        std::lock_guard<std::mutex> lock(blocking.mutex);
        blocking.go = true;
    }
    blocking.release.notify_all();
    first.join();
}

}  // namespace

int main() {
    test_budgets();
    test_serial_default();
    test_parallel_exact_once();
    test_exception_drain_and_recovery();
    test_overlap_rejected();
}
