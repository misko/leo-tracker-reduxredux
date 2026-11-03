#include "location.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <new>
#include <vector>

namespace {
struct Cell {
    double east;
    double north;
    double spacing;
    double priority;
    uint32_t depth;
    uint64_t serial;
    bool centre_inside;
};

struct Cached {
    leo_search_evaluation evaluation;
    double spacing;
    uint32_t depth;
};

bool cell_later(const Cell &left, const Cell &right) {
    if (left.priority != right.priority) {
        return left.priority > right.priority;
    }
    if (left.east != right.east) {
        return left.east > right.east;
    }
    if (left.north != right.north) {
        return left.north > right.north;
    }
    return left.serial > right.serial;
}

bool intersects(double east, double north, double spacing, double radius) {
    const double half = spacing / 2.0;
    return std::hypot(std::max(std::abs(east) - half, 0.0),
                      std::max(std::abs(north) - half, 0.0)) <= radius;
}

bool same_coordinate(double east, double north, const leo_search_evaluation &value) {
    return east == value.east_km && north == value.north_km;
}
}  // namespace

struct leo_search_context {
    uint32_t max_budget;
    size_t max_cells;
    uint64_t generation;
    leo_search_policy policy;
    uint64_t serial;
    bool active;
    bool cancelled;
    bool awaiting;
    bool initial_pending;
    double pending_parent_east;
    double pending_parent_north;
    std::vector<Cell> roots;
    std::vector<Cell> heap;
    std::vector<Cell> queued;
    std::vector<Cell> pending;
    std::vector<Cell> post_submit;
    std::vector<Cached> cache;
};

namespace {
bool valid_policy(const leo_search_context *context, const leo_search_policy *policy) {
    if (context == nullptr || policy == nullptr || policy->level_count == 0 ||
        policy->level_count > LEO_LOCATION_MAX_LEVELS || policy->radius_km <= 0.0 ||
        policy->region_size_km <= 0.0 || policy->radius_km > 500.0 ||
        policy->region_size_km > 1000.0 ||
        policy->radius_km > policy->region_size_km / 2.0 ||
        policy->budget_points == 0 || policy->budget_points > context->max_budget) {
        return false;
    }
    for (uint32_t index = 0; index < policy->level_count; ++index) {
        if (!std::isfinite(policy->levels_km[index]) || policy->levels_km[index] <= 0.0) {
            return false;
        }
        if (index != 0 &&
            std::abs(policy->levels_km[index - 1] / policy->levels_km[index] - 2.0) >
                1.0e-12) {
            return false;
        }
    }
    const double count = policy->region_size_km / policy->levels_km[0];
    return std::abs(count - std::round(count)) <= 1.0e-12 && count >= 1.0 && count <= 100.0;
}

const Cached *find_cache(const leo_search_context *context, double east, double north) {
    for (const Cached &entry : context->cache) {
        if (entry.evaluation.east_km == east && entry.evaluation.north_km == north) {
            return &entry;
        }
    }
    return nullptr;
}

bool was_queued(const leo_search_context *context, const Cell &cell) {
    for (const Cell &entry : context->queued) {
        if (entry.depth == cell.depth && entry.east == cell.east && entry.north == cell.north) {
            return true;
        }
    }
    return false;
}

leo_location_status queue_cell(
    leo_search_context *context, Cell cell, const Cached *parent) {
    if (was_queued(context, cell)) {
        return LEO_LOCATION_OK;
    }
    if (context->queued.size() >= context->max_cells ||
        context->heap.size() >= context->max_cells) {
        return LEO_LOCATION_CAPACITY;
    }
    const Cached *exact = find_cache(context, cell.east, cell.north);
    cell.priority = exact != nullptr ? exact->evaluation.weighted_mse_hz2
                                    : (parent != nullptr
                                           ? parent->evaluation.weighted_mse_hz2
                                           : 0.0);
    cell.serial = context->serial++;
    context->queued.push_back(cell);
    context->heap.push_back(cell);
    std::push_heap(context->heap.begin(), context->heap.end(), cell_later);
    return LEO_LOCATION_OK;
}

leo_location_status queue_post_submit(leo_search_context *context) {
    const Cached *parent = nullptr;
    if (!context->post_submit.empty()) {
        parent = find_cache(
            context, context->pending_parent_east, context->pending_parent_north);
    }
    for (const Cell &child : context->post_submit) {
        const leo_location_status status = queue_cell(context, child, parent);
        if (status != LEO_LOCATION_OK) {
            return status;
        }
    }
    context->post_submit.clear();
    return LEO_LOCATION_OK;
}

leo_location_status prepare_pending(leo_search_context *context) {
    while (context->cache.size() < context->policy.budget_points && !context->heap.empty()) {
        std::pop_heap(context->heap.begin(), context->heap.end(), cell_later);
        const Cell cell = context->heap.back();
        context->heap.pop_back();
        if (cell.depth + 1 >= context->policy.level_count) {
            continue;
        }
        const double spacing = context->policy.levels_km[cell.depth + 1];
        const double offset = cell.spacing / 4.0;
        static constexpr int signs[4][2] = {{-1, -1}, {-1, 1}, {1, -1}, {1, 1}};
        Cell children[4];
        size_t child_count = 0;
        for (const auto &sign : signs) {
            const double east = cell.east + sign[0] * offset;
            const double north = cell.north + sign[1] * offset;
            if (intersects(east, north, spacing, context->policy.radius_km)) {
                children[child_count++] = Cell{
                    east,
                    north,
                    spacing,
                    0.0,
                    cell.depth + 1,
                    0,
                    std::hypot(east, north) <= context->policy.radius_km,
                };
            }
        }
        const size_t available = context->policy.budget_points - context->cache.size();
        context->pending.clear();
        for (size_t child_index = 0; child_index < child_count; ++child_index) {
            const Cell &child = children[child_index];
            if (context->pending.size() >= available) {
                break;
            }
            if (child.centre_inside && find_cache(context, child.east, child.north) == nullptr) {
                context->pending.push_back(child);
            }
        }
        if (!context->pending.empty()) {
            context->post_submit.assign(children, children + child_count);
            context->pending_parent_east = cell.east;
            context->pending_parent_north = cell.north;
            return LEO_LOCATION_OK;
        }
        const Cached *parent = find_cache(context, cell.east, cell.north);
        for (size_t child_index = 0; child_index < child_count; ++child_index) {
            const Cell &child = children[child_index];
            const leo_location_status status = queue_cell(context, child, parent);
            if (status != LEO_LOCATION_OK) {
                return status;
            }
        }
    }
    return LEO_LOCATION_DONE;
}
}  // namespace

extern "C" leo_search_policy leo_search_default_policy(double radius_km) {
    leo_search_policy policy{};
    policy.radius_km = radius_km;
    policy.region_size_km = 1000.0;
    policy.level_count = 4;
    policy.levels_km[0] = 100.0;
    policy.levels_km[1] = 50.0;
    policy.levels_km[2] = 25.0;
    policy.levels_km[3] = 12.5;
    policy.budget_points = 400;
    return policy;
}

extern "C" leo_search_context *leo_search_context_create(uint32_t max_budget_points) {
    if (max_budget_points == 0 || max_budget_points > 100000) {
        return nullptr;
    }
    try {
        auto *context = new leo_search_context{};
        context->max_budget = max_budget_points;
        context->max_cells = static_cast<size_t>(max_budget_points) * 5 + 128;
        context->roots.reserve(100);
        context->heap.reserve(context->max_cells);
        context->queued.reserve(context->max_cells);
        context->pending.reserve(100);
        context->post_submit.reserve(4);
        context->cache.reserve(max_budget_points);
        return context;
    } catch (...) {
        return nullptr;
    }
}

extern "C" void leo_search_context_destroy(leo_search_context *context) {
    delete context;
}

extern "C" leo_location_status leo_search_begin(
    leo_search_context *context,
    uint64_t generation,
    const leo_search_policy *policy) {
    if (generation == 0 || !valid_policy(context, policy)) {
        return LEO_LOCATION_INVALID;
    }
    context->generation = generation;
    context->policy = *policy;
    context->serial = 0;
    context->active = true;
    context->cancelled = false;
    context->awaiting = false;
    context->initial_pending = true;
    context->roots.clear();
    context->heap.clear();
    context->queued.clear();
    context->pending.clear();
    context->post_submit.clear();
    context->cache.clear();
    const uint32_t count = static_cast<uint32_t>(
        std::llround(policy->region_size_km / policy->levels_km[0]));
    for (uint32_t north_index = 0; north_index < count; ++north_index) {
        const double north = (north_index + 0.5) * policy->levels_km[0] -
            policy->region_size_km / 2.0;
        for (uint32_t east_index = 0; east_index < count; ++east_index) {
            const double east = (east_index + 0.5) * policy->levels_km[0] -
                policy->region_size_km / 2.0;
            if (!intersects(east, north, policy->levels_km[0], policy->radius_km)) {
                continue;
            }
            const bool inside = std::hypot(east, north) <= policy->radius_km;
            const Cell cell{east, north, policy->levels_km[0], 0.0, 0, 0, inside};
            context->roots.push_back(cell);
            if (inside) {
                context->pending.push_back(cell);
            }
        }
    }
    if (context->pending.empty() || context->pending.size() > policy->budget_points) {
        context->active = false;
        return LEO_LOCATION_INVALID;
    }
    return LEO_LOCATION_OK;
}

extern "C" leo_location_status leo_search_next(
    leo_search_context *context,
    uint64_t generation,
    leo_search_point *points,
    uint32_t capacity,
    uint32_t *point_count) {
    if (context == nullptr || point_count == nullptr || !context->active) {
        return LEO_LOCATION_STATE;
    }
    if (generation != context->generation) {
        return LEO_LOCATION_STALE;
    }
    if (context->cancelled) {
        *point_count = 0;
        return LEO_LOCATION_CANCELLED;
    }
    if (context->awaiting) {
        return LEO_LOCATION_STATE;
    }
    if (context->pending.empty()) {
        const leo_location_status status = prepare_pending(context);
        if (status != LEO_LOCATION_OK) {
            *point_count = 0;
            return status;
        }
    }
    *point_count = static_cast<uint32_t>(context->pending.size());
    if (points == nullptr || capacity < context->pending.size()) {
        return LEO_LOCATION_CAPACITY;
    }
    for (size_t index = 0; index < context->pending.size(); ++index) {
        const Cell &cell = context->pending[index];
        points[index] = leo_search_point{cell.east, cell.north, cell.spacing, cell.depth};
    }
    context->awaiting = true;
    return LEO_LOCATION_OK;
}

extern "C" leo_location_status leo_search_submit(
    leo_search_context *context,
    uint64_t generation,
    const leo_search_evaluation *evaluations,
    uint32_t evaluation_count) {
    if (context == nullptr || !context->active || !context->awaiting || evaluations == nullptr) {
        return LEO_LOCATION_STATE;
    }
    if (generation != context->generation) {
        return LEO_LOCATION_STALE;
    }
    if (context->cancelled) {
        return LEO_LOCATION_CANCELLED;
    }
    if (evaluation_count != context->pending.size()) {
        return LEO_LOCATION_INVALID;
    }
    for (uint32_t index = 0; index < evaluation_count; ++index) {
        const Cell &cell = context->pending[index];
        const leo_search_evaluation &evaluation = evaluations[index];
        if (!same_coordinate(cell.east, cell.north, evaluation) ||
            !std::isfinite(evaluation.weighted_mse_hz2) ||
            evaluation.weighted_mse_hz2 < 0.0 ||
            find_cache(context, cell.east, cell.north) != nullptr ||
            context->cache.size() >= context->policy.budget_points) {
            return LEO_LOCATION_INVALID;
        }
    }
    for (uint32_t index = 0; index < evaluation_count; ++index) {
        context->cache.push_back(Cached{
            evaluations[index], context->pending[index].spacing, context->pending[index].depth});
    }
    context->pending.clear();
    context->awaiting = false;
    if (context->initial_pending) {
        context->initial_pending = false;
        for (const Cell &root : context->roots) {
            const leo_location_status status = queue_cell(
                context, root, find_cache(context, root.east, root.north));
            if (status != LEO_LOCATION_OK) {
                return status;
            }
        }
    } else {
        const leo_location_status status = queue_post_submit(context);
        if (status != LEO_LOCATION_OK) {
            return status;
        }
    }
    return LEO_LOCATION_OK;
}

extern "C" leo_location_status leo_search_cancel(
    leo_search_context *context, uint64_t generation) {
    if (context == nullptr || !context->active) {
        return LEO_LOCATION_STATE;
    }
    if (generation != context->generation) {
        return LEO_LOCATION_STALE;
    }
    context->cancelled = true;
    return LEO_LOCATION_OK;
}

extern "C" leo_location_status leo_search_get_result(
    const leo_search_context *context,
    uint64_t generation,
    leo_search_result *result) {
    if (context == nullptr || result == nullptr || !context->active) {
        return LEO_LOCATION_STATE;
    }
    if (generation != context->generation) {
        return LEO_LOCATION_STALE;
    }
    *result = leo_search_result{};
    result->generation = generation;
    result->evaluated_points = static_cast<uint32_t>(context->cache.size());
    result->deferred_cells = static_cast<uint32_t>(context->heap.size());
    result->cancelled = context->cancelled;
    result->complete = !context->cancelled && !context->awaiting &&
        context->pending.empty() && context->heap.empty();
    if (!context->cache.empty()) {
        const Cached *best = &context->cache[0];
        for (const Cached &candidate : context->cache) {
            const auto &left = candidate.evaluation;
            const auto &right = best->evaluation;
            if (left.weighted_mse_hz2 < right.weighted_mse_hz2 ||
                (left.weighted_mse_hz2 == right.weighted_mse_hz2 &&
                 (left.east_km < right.east_km ||
                  (left.east_km == right.east_km && left.north_km < right.north_km)))) {
                best = &candidate;
            }
        }
        result->has_incumbent = 1;
        result->incumbent = best->evaluation;
    }
    return LEO_LOCATION_OK;
}
