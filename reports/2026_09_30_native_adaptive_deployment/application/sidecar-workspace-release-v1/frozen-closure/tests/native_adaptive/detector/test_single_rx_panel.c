#define _POSIX_C_SOURCE 200809L

#include "native_glrt.h"
#include "single_rx_glrt.h"

#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { EDGE_LOWER = 0, EDGE_UPPER = 1, EDGE_COUNT = 2, MODE_COUNT = 2 };

typedef struct {
    void *exact_data;
    void *control_data;
    size_t template_count;
    leo_native_glrt *dual[MODE_COUNT];
    leo_single_rx_glrt *single[MODE_COUNT][2];
} edge_contexts;

static const char *const schedule_names[] = {
    "lower-000.tsv", "lower-008.tsv", "lower-016.tsv", "lower-024.tsv",
    "lower-032.tsv", "lower-040.tsv", "upper-000.tsv", "upper-008.tsv",
    "upper-016.tsv", "upper-024.tsv", "upper-032.tsv",
};

static int read_exact(const char *path, void **data, size_t *size)
{
    FILE *file = fopen(path, "rb");
    if (!file || fseek(file, 0, SEEK_END)) return -1;
    long end = ftell(file);
    if (end <= 0 || fseek(file, 0, SEEK_SET)) {
        fclose(file);
        return -1;
    }
    void *value = malloc((size_t)end);
    if (!value || fread(value, 1, (size_t)end, file) != (size_t)end ||
        fgetc(file) != EOF) {
        free(value);
        fclose(file);
        return -1;
    }
    fclose(file);
    *data = value;
    *size = (size_t)end;
    return 0;
}

static const char *base_name(const char *path)
{
    const char *slash = strrchr(path, '/');
    return slash ? slash + 1 : path;
}

static int candidate_equal(const leo_native_glrt_candidate *expected,
    const leo_native_glrt_candidate *actual, const char **field)
{
#define CHECK_FIELD(name) \
    do { \
        if (memcmp(&expected->name, &actual->name, sizeof(expected->name))) { \
            *field = #name; \
            return 0; \
        } \
    } while (0)
    CHECK_FIELD(coarse_epoch);
    CHECK_FIELD(coarse_bin);
    CHECK_FIELD(refined_epoch);
    CHECK_FIELD(frame_support);
    CHECK_FIELD(glrt_complete);
    CHECK_FIELD(conditioned_fallback);
    CHECK_FIELD(refinement_skipped);
    CHECK_FIELD(coarse_cfo_hz);
    CHECK_FIELD(fine_cfo_hz);
    CHECK_FIELD(conditioned_cfo_hz);
    CHECK_FIELD(epoch);
    CHECK_FIELD(acquired_cfo_hz);
    CHECK_FIELD(tracking_cfo_hz);
    CHECK_FIELD(exact_score);
    CHECK_FIELD(control_score);
    CHECK_FIELD(margin);
    CHECK_FIELD(acquire_score);
    CHECK_FIELD(verify_score);
    CHECK_FIELD(verify_control_score);
    CHECK_FIELD(conditioned_score);
    CHECK_FIELD(coarse_score);
    CHECK_FIELD(fractional_epoch_status);
    CHECK_FIELD(fractional_epoch_offset_samples);
    CHECK_FIELD(fractional_epoch_log_curvature);
    CHECK_FIELD(fractional_epoch_exact_grid);
    CHECK_FIELD(fractional_epoch_control_grid);
    CHECK_FIELD(fractional_exact_score);
    CHECK_FIELD(fractional_control_score);
    CHECK_FIELD(fractional_margin);
    CHECK_FIELD(fractional_residual_cfo_hz);
    CHECK_FIELD(fractional_tracking_cfo_hz);
#undef CHECK_FIELD
    return 1;
}

static int row_equal(const leo_native_glrt_row *expected,
    const leo_native_glrt_row *actual, int receiver, const char **field,
    int *candidate_index)
{
#define CHECK_VALUE(name) \
    do { \
        if (expected->name != actual->name) { \
            *field = #name; \
            return 0; \
        } \
    } while (0)
    if (expected->receiver_id != receiver || actual->receiver_id != 0) {
        *field = "receiver_id";
        return 0;
    }
    CHECK_VALUE(probe_index);
    CHECK_VALUE(probe_start_ms);
    CHECK_VALUE(proposal_executed);
    CHECK_VALUE(proposal_tracking_fallback);
    CHECK_VALUE(proposal_neighbor_matches);
    CHECK_VALUE(candidate_count);
    CHECK_VALUE(retained_peak_count);
    CHECK_VALUE(coarse_gate_skipped_count);
    CHECK_VALUE(conditioned_fallback_count);
    CHECK_VALUE(actual_executed_glrt_calls);
    CHECK_VALUE(glrt_cache_hits);
    CHECK_VALUE(conditioned_cache_hits);
    CHECK_VALUE(fine_fft_cache_entries);
    CHECK_VALUE(fine_fft_cache_hits);
    CHECK_VALUE(fine_precision_calls);
    CHECK_VALUE(fine_precision_guard_checks);
    CHECK_VALUE(fine_precision_fallbacks);
    CHECK_VALUE(fine_precision_nonfinite_fallbacks);
    CHECK_VALUE(fine_precision_near_tie_fallbacks);
    CHECK_VALUE(fine_precision_interpolation_fallbacks);
    CHECK_VALUE(conditioned_bins_screened);
    CHECK_VALUE(conditioned_bins_rechecked);
#undef CHECK_VALUE
    for (int index = 0; index < expected->candidate_count; ++index) {
        if (!candidate_equal(&expected->candidates[index],
                &actual->candidates[index], field)) {
            *candidate_index = index;
            return 0;
        }
    }
    return 1;
}

static int compare_receiver(const leo_native_glrt_result *dual,
    const leo_native_glrt_result *single, int receiver, int mode,
    size_t panel_index, const char *raw_name)
{
    if (dual->row_count != 2 * single->row_count) {
        fprintf(stderr,
            "panel mismatch: mode=%d item=%zu raw=%s receiver=%d field=row_count "
            "dual=%zu single=%zu\n",
            mode, panel_index, raw_name, receiver, dual->row_count,
            single->row_count);
        return 0;
    }
    for (size_t row = 0; row < single->row_count; ++row) {
        const leo_native_glrt_row *expected =
            &dual->rows[2 * row + (size_t)receiver];
        const char *field = NULL;
        int candidate_index = -1;
        if (!row_equal(expected, &single->rows[row], receiver, &field,
                &candidate_index)) {
            fprintf(stderr,
                "panel mismatch: mode=%d item=%zu raw=%s receiver=%d probe=%zu "
                "candidate=%d field=%s\n",
                mode, panel_index, raw_name, receiver, row, candidate_index,
                field ? field : "unknown");
            return 0;
        }
    }
    return 1;
}

static int create_edge(edge_contexts *edge, const char *fixture_root,
    const char *name)
{
    char exact_path[PATH_MAX];
    char control_path[PATH_MAX];
    if (snprintf(exact_path, sizeof(exact_path), "%s/%s-exact.c128",
            fixture_root, name) >= (int)sizeof(exact_path) ||
        snprintf(control_path, sizeof(control_path), "%s/%s-control.c128",
            fixture_root, name) >= (int)sizeof(control_path))
        return -1;
    size_t exact_size = 0;
    size_t control_size = 0;
    if (read_exact(exact_path, &edge->exact_data, &exact_size) ||
        read_exact(control_path, &edge->control_data, &control_size) ||
        exact_size != control_size ||
        exact_size % sizeof(leo_native_glrt_complex))
        return -1;
    edge->template_count = exact_size / sizeof(leo_native_glrt_complex);
    const uint32_t modes[MODE_COUNT] = {
        LEO_NATIVE_GLRT_MODE_ORDINARY,
        LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH,
    };
    for (int mode = 0; mode < MODE_COUNT; ++mode) {
        if (leo_native_glrt_create_with_mode(&edge->dual[mode], 2500000,
                edge->exact_data, edge->control_data, edge->template_count,
                modes[mode]))
            return -1;
        for (int receiver = 0; receiver < 2; ++receiver)
            if (leo_single_rx_glrt_create_with_mode(
                    &edge->single[mode][receiver], 2500000,
                    edge->exact_data, edge->control_data,
                    edge->template_count, modes[mode]))
                return -1;
    }
    return 0;
}

static void destroy_edge(edge_contexts *edge)
{
    for (int mode = 0; mode < MODE_COUNT; ++mode) {
        for (int receiver = 0; receiver < 2; ++receiver)
            if (edge->single[mode][receiver])
                (void)leo_single_rx_glrt_destroy(edge->single[mode][receiver]);
        if (edge->dual[mode]) (void)leo_native_glrt_destroy(edge->dual[mode]);
    }
    free(edge->control_data);
    free(edge->exact_data);
}

static int run_item(edge_contexts *edge, const char *fixture_root,
    const char *raw_field, int mode, size_t panel_index)
{
    char raw_path[PATH_MAX];
    const char *raw_name = base_name(raw_field);
    if (snprintf(raw_path, sizeof(raw_path), "%s/%s", fixture_root,
            raw_name) >= (int)sizeof(raw_path))
        return -1;
    void *dual_data = NULL;
    size_t dual_size = 0;
    size_t complex_times = 0;
    size_t row_count = 0;
    if (read_exact(raw_path, &dual_data, &dual_size) ||
        leo_native_glrt_layout(2500000, 120, 120, &complex_times,
            &row_count) ||
        dual_size != 4 * complex_times * sizeof(int16_t)) {
        fprintf(stderr, "invalid panel raw: item=%zu path=%s\n", panel_index,
            raw_path);
        free(dual_data);
        return -1;
    }
    int16_t *single[2] = {
        malloc(2 * complex_times * sizeof(int16_t)),
        malloc(2 * complex_times * sizeof(int16_t)),
    };
    if (!single[0] || !single[1]) {
        free(single[1]);
        free(single[0]);
        free(dual_data);
        return -1;
    }
    const int16_t *dual_samples = dual_data;
    for (size_t sample = 0; sample < complex_times; ++sample)
        for (int receiver = 0; receiver < 2; ++receiver) {
            single[receiver][2 * sample] =
                dual_samples[4 * sample + 2 * (size_t)receiver];
            single[receiver][2 * sample + 1] =
                dual_samples[4 * sample + 2 * (size_t)receiver + 1];
        }
    leo_native_glrt_result dual_result = {0};
    int status = leo_native_glrt_analyze(edge->dual[mode], dual_samples,
        complex_times, 120, 120, &dual_result);
    for (int receiver = 0; receiver < 2 && !status; ++receiver) {
        leo_native_glrt_result result = {0};
        status = leo_single_rx_glrt_analyze(edge->single[mode][receiver],
            single[receiver], complex_times, 120, 120, &result);
        if (!status && !compare_receiver(&dual_result, &result, receiver, mode,
                panel_index, raw_name))
            status = -1;
    }
    if (status)
        fprintf(stderr, "panel analysis failed: mode=%d item=%zu raw=%s status=%d\n",
            mode, panel_index, raw_name, status);
    free(single[1]);
    free(single[0]);
    free(dual_data);
    return status ? -1 : 0;
}

static int run_panel(edge_contexts edges[EDGE_COUNT], const char *fixture_root,
    const char *schedule_root, int mode, size_t *panel_count)
{
    size_t count = 0;
    for (size_t schedule = 0;
         schedule < sizeof(schedule_names) / sizeof(schedule_names[0]);
         ++schedule) {
        char path[PATH_MAX];
        if (snprintf(path, sizeof(path), "%s/%s", schedule_root,
                schedule_names[schedule]) >= (int)sizeof(path))
            return -1;
        FILE *file = fopen(path, "r");
        if (!file) return -1;
        char line[8192];
        while (fgets(line, sizeof(line), file)) {
            char *save = NULL;
            char *field = strtok_r(line, "\t\n", &save);
            int column = 0;
            const char *raw = NULL;
            while (field) {
                if (column == 6) {
                    raw = field;
                    break;
                }
                ++column;
                field = strtok_r(NULL, "\t\n", &save);
            }
            if (!raw || run_item(&edges[schedule_names[schedule][0] == 'u' ?
                    EDGE_UPPER : EDGE_LOWER], fixture_root, raw, mode, count)) {
                fclose(file);
                return -1;
            }
            ++count;
        }
        if (ferror(file)) {
            fclose(file);
            return -1;
        }
        fclose(file);
    }
    if (count != 80) {
        fprintf(stderr, "panel inventory mismatch: got=%zu expected=80\n", count);
        return -1;
    }
    *panel_count = count;
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 3) return 2;
    edge_contexts edges[EDGE_COUNT] = {{0}};
    if (create_edge(&edges[EDGE_LOWER], argv[1], "lower") ||
        create_edge(&edges[EDGE_UPPER], argv[1], "upper")) {
        destroy_edge(&edges[EDGE_UPPER]);
        destroy_edge(&edges[EDGE_LOWER]);
        return 3;
    }
    size_t ordinary_count = 0;
    size_t fractional_count = 0;
    int status = run_panel(edges, argv[1], argv[2], 0, &ordinary_count) ||
        run_panel(edges, argv[1], argv[2], 1, &fractional_count);
    destroy_edge(&edges[EDGE_UPPER]);
    destroy_edge(&edges[EDGE_LOWER]);
    if (status) return 4;
    printf("single-rx portable panel passed: ordinary=%zu fractional=%zu "
           "receivers=2\n", ordinary_count, fractional_count);
    return 0;
}
