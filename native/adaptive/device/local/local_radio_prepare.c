#include "local_radio_prepare.h"
#include "local_source.h"

#include <errno.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

struct leo_local_radio_preparation {
    leo_local_radio_prepare_ops ops;
    leo_local_owner *owner;
    leo_local_radio_prepare_receipt receipt;
};

static bool ops_valid(const leo_local_radio_prepare_ops *ops)
{
    return ops && ops->open && ops->close && ops->read_settings &&
        ops->configure_geometry && ops->restore_settings &&
        ops->get_kernel_buffers && ops->set_kernel_buffers &&
        ops->read_active_profile && ops->write_frequency &&
        ops->read_frequency && ops->store_profile && ops->save_profile &&
        ops->load_profile && ops->recall_profile;
}

static bool config_valid(const leo_local_radio_prepare_config *config)
{
    uint32_t used = 0U, i;

    if (!config || config->abi_version != LEO_LOCAL_RADIO_PREPARE_ABI_VERSION ||
        config->sample_rate_hz < 520833U || config->sample_rate_hz > 61440000U ||
        config->analog_bandwidth_hz < 200000U ||
        config->analog_bandwidth_hz > 56000000U ||
        (config->receiver_count != 1U && config->receiver_count != 2U) ||
        config->target_count == 0U ||
        config->target_count > LEO_LOCAL_RADIO_MAX_TARGETS)
        return false;
    for (i = 0U; i < config->target_count; ++i) {
        uint32_t bit;
        if (config->targets[i].profile > 7U ||
            config->targets[i].frequency_hz < UINT64_C(70000000) ||
            config->targets[i].frequency_hz > UINT64_C(6000000000))
            return false;
        bit = 1U << config->targets[i].profile;
        if (used & bit)
            return false;
        used |= bit;
    }
    return true;
}

static bool settings_equal(const leo_local_radio_settings *a,
    const leo_local_radio_settings *b)
{
    uint32_t i;
    if (!(a->center_frequency_hz == b->center_frequency_hz &&
        a->sample_rate_hz == b->sample_rate_hz &&
        a->capture_sample_rate_hz == b->capture_sample_rate_hz &&
        a->analog_bandwidth_hz == b->analog_bandwidth_hz &&
        a->receiver_mask == b->receiver_mask &&
        !memcmp(a->gain_mode, b->gain_mode, sizeof(a->gain_mode))))
        return false;
    /* AGC gain is an observation. Only manual gain is settable state. */
    for (i = 0U; i < 2U; ++i)
        if (!strcmp(a->gain_mode[i], "manual") &&
            a->gain_millidb[i] != b->gain_millidb[i])
            return false;
    return true;
}

static uint32_t crc32(const uint8_t *bytes, size_t count)
{
    uint32_t crc = UINT32_C(0xffffffff);
    size_t i;
    for (i = 0; i < count; ++i) {
        unsigned bit;
        crc ^= bytes[i];
        for (bit = 0; bit < 8U; ++bit)
            crc = (crc >> 1U) ^ (UINT32_C(0xedb88320) &
                (uint32_t)-(int32_t)(crc & 1U));
    }
    return crc ^ UINT32_C(0xffffffff);
}

static int exit_fastlock(const leo_local_radio_prepare_ops *ops, void *radio,
    uint64_t cached_frequency, uint64_t target_frequency)
{
    uint64_t observed = 0U;
    int32_t active = 0;
    uint64_t transition = cached_frequency == target_frequency ?
        (target_frequency <= UINT64_C(5999999998) ?
            target_frequency + 2U : target_frequency - 2U) : target_frequency;
    int ret = ops->write_frequency(ops->context, radio, transition);
    if (!ret) ret = ops->read_frequency(ops->context, radio, &observed);
    if (!ret && observed != transition) ret = -EPROTO;
    if (!ret && transition != target_frequency)
        ret = ops->write_frequency(ops->context, radio, target_frequency);
    if (!ret) ret = ops->read_active_profile(ops->context, radio, &active);
    if (!ret) ret = ops->read_frequency(ops->context, radio, &observed);
    if (!ret && (active != -1 || observed != target_frequency)) ret = -EPROTO;
    return ret;
}

static int restore_open_radio(const leo_local_radio_prepare_ops *ops, void *radio,
    const leo_local_radio_settings *settings, uint32_t kernel_buffers,
    leo_local_radio_restore_receipt *receipt)
{
    leo_local_radio_settings observed;
    uint32_t observed_buffers = 0U;
    int32_t active = 0;
    int ret;

    memset(&observed, 0, sizeof(observed));
    ret = ops->restore_settings(ops->context, radio, settings, &observed);
    if (!ret && !settings_equal(settings, &observed)) ret = -EPROTO;
    {
        int step = ops->set_kernel_buffers(ops->context, radio, kernel_buffers,
            &observed_buffers);
        if (!step && observed_buffers != kernel_buffers) step = -EPROTO;
        if (!ret && step) ret = step;
    }
    {
        int step = ops->read_active_profile(ops->context, radio, &active);
        if (!step && active != -1) step = -EPROTO;
        if (!ret && step) ret = step;
    }
    if (receipt) {
        memset(receipt, 0, sizeof(*receipt));
        receipt->expected = *settings;
        receipt->observed = observed;
        receipt->expected_kernel_buffers = kernel_buffers;
        receipt->observed_kernel_buffers = observed_buffers;
        receipt->fastlock_inactive = active == -1;
    }
    return ret;
}

int leo_local_radio_preflight_inactive(const leo_local_radio_prepare_ops *ops)
{
    void *radio = NULL;
    int32_t active = 0;
    int close_status, ret;
    if (!ops_valid(ops)) return -EINVAL;
    ret = ops->open(ops->context, &radio);
    if (!ret) ret = ops->read_active_profile(ops->context, radio, &active);
    close_status = radio ? ops->close(ops->context, radio) : 0;
    if (!ret && active != -1) ret = -EBUSY;
    return ret ? ret : close_status;
}

int leo_local_radio_prepare_owned(const leo_local_radio_prepare_config *config,
    const leo_local_radio_prepare_ops *ops,
    leo_local_owner *exclusive_owner,
    leo_local_radio_preparation **preparation,
    leo_local_radio_prepare_receipt *receipt)
{
    leo_local_radio_preparation *state = NULL;
    leo_local_radio_restore_receipt ignored = { 0 };
    void *radio = NULL;
    int32_t active = 0;
    uint64_t frequency = 0U;
    uint32_t i;
    int close_status, cleanup_status, ret;
    bool snapshotted = false, mutated = false;

    if (!preparation || !receipt || !leo_local_owner_is_live(exclusive_owner))
        return -EINVAL;
    *preparation = NULL;
    memset(receipt, 0, sizeof(*receipt));
    if (!config_valid(config) || !ops_valid(ops))
        return -EINVAL;
    state = calloc(1, sizeof(*state));
    if (!state)
        return -ENOMEM;
    state->ops = *ops;
    state->owner = exclusive_owner;
    ret = ops->open(ops->context, &radio);
    if (ret)
        goto fail;
    ret = ops->read_settings(ops->context, radio, &state->receipt.original);
    if (ret)
        goto close_fail;
    ret = ops->get_kernel_buffers(ops->context, radio,
        &state->receipt.original_kernel_buffers);
    if (ret)
        goto close_fail;
    snapshotted = true;
    ret = ops->read_active_profile(ops->context, radio, &active);
    if (ret || active != -1) {
        if (!ret) ret = -EBUSY;
        goto close_fail;
    }
    mutated = true;
    ret = ops->configure_geometry(ops->context, radio, config,
        &state->receipt.configured);
    if (ret)
        goto restore_fail;
    if (state->receipt.configured.sample_rate_hz != config->sample_rate_hz ||
        state->receipt.configured.capture_sample_rate_hz != config->sample_rate_hz ||
        state->receipt.configured.analog_bandwidth_hz !=
            config->analog_bandwidth_hz ||
        state->receipt.configured.receiver_mask !=
            ((1U << config->receiver_count) - 1U)) {
        ret = -EPROTO;
        goto restore_fail;
    }
    for (i = 0U; i < config->receiver_count; ++i) {
        if (strcmp(state->receipt.configured.gain_mode[i], "manual") ||
            state->receipt.configured.gain_millidb[i] !=
                config->manual_gain_millidb) {
            ret = -EPROTO;
            goto restore_fail;
        }
    }
    ret = ops->set_kernel_buffers(ops->context, radio,
        LEO_LOCAL_RADIO_KERNEL_BUFFERS,
        &state->receipt.configured_kernel_buffers);
    if (ret)
        goto restore_fail;
    if (state->receipt.configured_kernel_buffers !=
        LEO_LOCAL_RADIO_KERNEL_BUFFERS) {
        ret = -EPROTO;
        goto restore_fail;
    }
    state->receipt.target_count = config->target_count;
    for (i = 0U; i < config->target_count; ++i) {
        leo_local_radio_prepared_target *target = &state->receipt.targets[i];
        target->profile = config->targets[i].profile;
        target->frequency_hz = config->targets[i].frequency_hz;
        ret = ops->write_frequency(ops->context, radio, target->frequency_hz);
        if (!ret)
            ret = ops->read_frequency(ops->context, radio, &frequency);
        if (ret || frequency != target->frequency_hz) {
            if (!ret) ret = -EPROTO;
            goto restore_fail;
        }
        ret = ops->store_profile(ops->context, radio, target->profile,
            target->profile_bytes);
        if (!ret) {
            uint8_t saved[LEO_LOCAL_RADIO_PROFILE_BYTES];
            ret = ops->save_profile(ops->context, radio, target->profile, saved);
            if (!ret && memcmp(saved, target->profile_bytes, sizeof(saved)))
                ret = -EPROTO;
        }
        if (!ret)
            ret = ops->recall_profile(ops->context, radio, target->profile);
        if (!ret)
            ret = ops->read_active_profile(ops->context, radio, &active);
        if (!ret && active != (int32_t)target->profile)
            ret = -EPROTO;
        if (ret)
            goto restore_fail;
    }
    ret = exit_fastlock(ops, radio,
        config->targets[config->target_count - 1U].frequency_hz,
        config->targets[0].frequency_hz);
    if (ret)
        goto restore_fail;
    for (i = 0U; i < config->target_count; ++i) {
        uint8_t saved[LEO_LOCAL_RADIO_PROFILE_BYTES];
        leo_local_radio_prepared_target *target = &state->receipt.targets[i];
        ret = ops->load_profile(ops->context, radio, target->profile,
            target->profile_bytes);
        if (!ret)
            ret = ops->save_profile(ops->context, radio, target->profile, saved);
        if (!ret && memcmp(saved, target->profile_bytes, sizeof(saved)))
            ret = -EPROTO;
        if (ret)
            goto restore_fail;
    }
    for (i = 0U; i < config->target_count; ++i) {
        ret = ops->recall_profile(ops->context, radio,
            config->targets[i].profile);
        if (!ret) ret = ops->read_active_profile(ops->context, radio, &active);
        if (!ret && active != (int32_t)config->targets[i].profile)
            ret = -EPROTO;
        if (ret)
            goto restore_fail;
    }
    for (i = 0U; i < config->target_count; ++i) {
        uint8_t saved[LEO_LOCAL_RADIO_PROFILE_BYTES];
        leo_local_radio_prepared_target *target = &state->receipt.targets[i];
        ret = ops->load_profile(ops->context, radio, target->profile,
            target->profile_bytes);
        if (!ret)
            ret = ops->save_profile(ops->context, radio, target->profile, saved);
        if (!ret && memcmp(saved, target->profile_bytes, sizeof(saved)))
            ret = -EPROTO;
        if (ret)
            goto restore_fail;
    }
    ret = exit_fastlock(ops, radio, config->targets[0].frequency_hz,
        config->targets[0].frequency_hz);
    if (ret)
        goto restore_fail;
    for (i = 0U; i < config->target_count; ++i) {
        state->receipt.targets[i].profile_crc32 = crc32(
            state->receipt.targets[i].profile_bytes,
            LEO_LOCAL_RADIO_PROFILE_BYTES);
        if (!state->receipt.targets[i].profile_crc32) {
            ret = -EPROTO;
            goto restore_fail;
        }
    }
    close_status = ops->close(ops->context, radio);
    radio = NULL;
    if (close_status) {
        ret = close_status;
        *receipt = state->receipt;
        *preparation = state;
        return ret;
    }
    *receipt = state->receipt;
    *preparation = state;
    return 0;

restore_fail:
    cleanup_status = snapshotted && mutated ? restore_open_radio(ops, radio,
        &state->receipt.original, state->receipt.original_kernel_buffers,
        &ignored) : 0;
    state->receipt.cleanup_attempted = snapshotted && mutated;
    state->receipt.cleanup_status = cleanup_status;
    state->receipt.cleanup_observed = ignored.observed;
    state->receipt.cleanup_observed_kernel_buffers =
        ignored.observed_kernel_buffers;
    state->receipt.cleanup_fastlock_inactive = ignored.fastlock_inactive;
    close_status = ops->close(ops->context, radio);
    radio = NULL;
    if (cleanup_status || close_status) {
        if (!state->receipt.cleanup_status)
            state->receipt.cleanup_status = close_status;
        ret = -EUCLEAN;
        *receipt = state->receipt;
        *preparation = state;
        return ret;
    }
    *receipt = state->receipt;
    goto fail;
close_fail:
    close_status = ops->close(ops->context, radio);
    radio = NULL;
    if (close_status) ret = close_status;
fail:
    free(state);
    return ret;
}

int leo_local_radio_restore(leo_local_radio_preparation **preparation_pointer,
    leo_local_owner *exclusive_owner,
    leo_local_radio_restore_receipt *receipt)
{
    leo_local_radio_preparation *preparation;
    const leo_local_radio_prepare_ops *ops;
    void *radio = NULL;
    int close_status, ret;

    if (!preparation_pointer || !*preparation_pointer || !receipt ||
        !leo_local_owner_is_live(exclusive_owner) ||
        (*preparation_pointer)->owner != exclusive_owner)
        return -EINVAL;
    preparation = *preparation_pointer;
    memset(receipt, 0, sizeof(*receipt));
    ops = &preparation->ops;
    ret = ops->open(ops->context, &radio);
    if (!ret)
        ret = restore_open_radio(ops, radio, &preparation->receipt.original,
            preparation->receipt.original_kernel_buffers, receipt);
    close_status = radio ? ops->close(ops->context, radio) : 0;
    if (!ret && !close_status) {
        free(preparation);
        *preparation_pointer = NULL;
        return 0;
    }
    return ret ? ret : close_status;
}
