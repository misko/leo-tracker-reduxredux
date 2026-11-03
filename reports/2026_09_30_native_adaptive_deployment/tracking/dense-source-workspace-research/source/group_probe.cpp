#include "group_probe.hpp"

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <new>

namespace {

thread_local bool active = false;
thread_local std::uint64_t call_allocations = 0;
thread_local std::uint64_t call_bytes = 0;

std::atomic<std::uint64_t> calls{};
std::atomic<std::uint64_t> input_indexes{};
std::atomic<std::uint64_t> distinct_keys{};
std::atomic<std::uint64_t> fallback_indexes{};
std::atomic<std::uint64_t> allocation_calls{};
std::atomic<std::uint64_t> allocation_bytes{};
std::atomic<std::uint64_t> maximum_input_indexes{};
std::atomic<std::uint64_t> maximum_distinct_keys{};
std::atomic<std::uint64_t> maximum_call_allocations{};
std::atomic<std::uint64_t> maximum_call_bytes{};

void maximum(std::atomic<std::uint64_t>& target, std::uint64_t value) noexcept {
    auto previous = target.load(std::memory_order_relaxed);
    while (previous < value &&
           !target.compare_exchange_weak(previous, value, std::memory_order_relaxed)) {}
}

void account(std::size_t bytes) noexcept {
    if (active) {
        ++call_allocations;
        call_bytes += bytes;
    }
}

void* allocate(std::size_t bytes) {
    const std::size_t actual = bytes == 0 ? 1 : bytes;
    void* memory = std::malloc(actual);
    if (memory == nullptr) throw std::bad_alloc{};
    account(bytes);
    return memory;
}

void* allocate_aligned(std::size_t bytes, std::size_t alignment) {
    const std::size_t actual = bytes == 0 ? alignment : bytes;
    void* memory = nullptr;
    if (posix_memalign(&memory, alignment, actual) != 0) throw std::bad_alloc{};
    account(bytes);
    return memory;
}

struct Reporter {
    ~Reporter() {
        std::fprintf(
            stderr,
            "GROUP_PROBE {\"calls\":%llu,\"input_indexes\":%llu,"
            "\"distinct_keys\":%llu,\"fallback_indexes\":%llu,"
            "\"allocation_calls\":%llu,\"allocation_bytes\":%llu,"
            "\"maximum_input_indexes\":%llu,\"maximum_distinct_keys\":%llu,"
            "\"maximum_call_allocations\":%llu,\"maximum_call_bytes\":%llu}\n",
            static_cast<unsigned long long>(calls.load()),
            static_cast<unsigned long long>(input_indexes.load()),
            static_cast<unsigned long long>(distinct_keys.load()),
            static_cast<unsigned long long>(fallback_indexes.load()),
            static_cast<unsigned long long>(allocation_calls.load()),
            static_cast<unsigned long long>(allocation_bytes.load()),
            static_cast<unsigned long long>(maximum_input_indexes.load()),
            static_cast<unsigned long long>(maximum_distinct_keys.load()),
            static_cast<unsigned long long>(maximum_call_allocations.load()),
            static_cast<unsigned long long>(maximum_call_bytes.load()));
    }
} reporter;

}  // namespace

void* operator new(std::size_t bytes) { return allocate(bytes); }
void* operator new[](std::size_t bytes) { return allocate(bytes); }
void operator delete(void* memory) noexcept { std::free(memory); }
void operator delete[](void* memory) noexcept { std::free(memory); }
void operator delete(void* memory, std::size_t) noexcept { std::free(memory); }
void operator delete[](void* memory, std::size_t) noexcept { std::free(memory); }
void* operator new(std::size_t bytes, std::align_val_t alignment) {
    return allocate_aligned(bytes, static_cast<std::size_t>(alignment));
}
void* operator new[](std::size_t bytes, std::align_val_t alignment) {
    return allocate_aligned(bytes, static_cast<std::size_t>(alignment));
}
void operator delete(void* memory, std::align_val_t) noexcept { std::free(memory); }
void operator delete[](void* memory, std::align_val_t) noexcept { std::free(memory); }
void operator delete(void* memory, std::size_t, std::align_val_t) noexcept { std::free(memory); }
void operator delete[](void* memory, std::size_t, std::align_val_t) noexcept { std::free(memory); }

namespace leo_group_probe {

Scope::Scope(std::size_t indexes) noexcept : input_indexes_(indexes) {
    call_allocations = 0;
    call_bytes = 0;
    active = true;
}

Scope::~Scope() noexcept {
    active = false;
    calls.fetch_add(1, std::memory_order_relaxed);
    input_indexes.fetch_add(input_indexes_, std::memory_order_relaxed);
    distinct_keys.fetch_add(distinct_keys_, std::memory_order_relaxed);
    fallback_indexes.fetch_add(fallback_indexes_, std::memory_order_relaxed);
    allocation_calls.fetch_add(call_allocations, std::memory_order_relaxed);
    allocation_bytes.fetch_add(call_bytes, std::memory_order_relaxed);
    maximum(maximum_input_indexes, input_indexes_);
    maximum(maximum_distinct_keys, distinct_keys_);
    maximum(maximum_call_allocations, call_allocations);
    maximum(maximum_call_bytes, call_bytes);
}

void Scope::finish(std::size_t keys, std::size_t fallbacks) noexcept {
    distinct_keys_ = keys;
    fallback_indexes_ = fallbacks;
}

}  // namespace leo_group_probe
