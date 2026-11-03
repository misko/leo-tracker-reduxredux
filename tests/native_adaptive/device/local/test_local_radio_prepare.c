#include "local_radio_prepare.h"

#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

struct fake_radio {
    leo_local_radio_settings settings;
    uint32_t kernel_buffers;
    uint8_t slots[8][LEO_LOCAL_RADIO_PROFILE_BYTES];
    int32_t active;
    int opens, closes, recalls, loads, ordinary_writes;
    int fail_recall;
    int lie_gain;
    uint64_t cached_frequency;
};

int leo_local_owner_is_live(const leo_local_owner *owner)
{
    return owner != NULL;
}

static void initial_settings(leo_local_radio_settings *value)
{
    memset(value, 0, sizeof(*value));
    value->center_frequency_hz = UINT64_C(915000000);
    value->sample_rate_hz = 1000000U;
    value->capture_sample_rate_hz = 1000000U;
    value->analog_bandwidth_hz = 1200000U;
    value->receiver_mask = 1U;
    strcpy(value->gain_mode[0], "slow_attack");
    value->gain_millidb[0] = 17000;
}

static int fake_open(void *context, void **out)
{
    struct fake_radio *radio = context;
    ++radio->opens;
    *out = radio;
    return 0;
}
static int fake_close(void *context, void *opaque)
{
    struct fake_radio *radio = context;
    assert(opaque == radio);
    ++radio->closes;
    return 0;
}
static int fake_read(void *context, void *opaque, leo_local_radio_settings *out)
{
    struct fake_radio *radio = context;
    assert(opaque == radio);
    *out = radio->settings;
    return 0;
}
static int fake_configure(void *context, void *opaque,
    const leo_local_radio_prepare_config *config, leo_local_radio_settings *out)
{
    struct fake_radio *radio = context;
    unsigned i;
    assert(opaque == radio);
    radio->settings.sample_rate_hz = config->sample_rate_hz;
    radio->settings.capture_sample_rate_hz = config->sample_rate_hz;
    radio->settings.analog_bandwidth_hz = config->analog_bandwidth_hz;
    radio->settings.receiver_mask = (1U << config->receiver_count) - 1U;
    for (i = 0; i < config->receiver_count; ++i) {
        strcpy(radio->settings.gain_mode[i], "manual");
        radio->settings.gain_millidb[i] = config->manual_gain_millidb;
    }
    *out = radio->settings;
    if (radio->lie_gain) strcpy(out->gain_mode[0], "slow_attack");
    return 0;
}
static int fake_restore(void *context, void *opaque,
    const leo_local_radio_settings *expected, leo_local_radio_settings *out)
{
    struct fake_radio *radio = context;
    assert(opaque == radio);
    radio->settings = *expected;
    radio->cached_frequency = expected->center_frequency_hz;
    radio->active = -1;
    *out = radio->settings;
    return 0;
}
static int fake_get_buffers(void *context, void *opaque, uint32_t *count)
{
    struct fake_radio *radio = context;
    assert(opaque == radio);
    *count = radio->kernel_buffers;
    return 0;
}
static int fake_set_buffers(void *context, void *opaque, uint32_t requested,
    uint32_t *observed)
{
    struct fake_radio *radio = context;
    assert(opaque == radio);
    radio->kernel_buffers = requested;
    *observed = requested;
    return 0;
}
static int fake_active(void *context, void *opaque, int32_t *active)
{
    struct fake_radio *radio = context;
    assert(opaque == radio);
    *active = radio->active;
    return 0;
}
static int fake_write_frequency(void *context, void *opaque, uint64_t frequency)
{
    struct fake_radio *radio = context;
    assert(opaque == radio);
    radio->settings.center_frequency_hz = frequency;
    if (radio->active < 0 || radio->cached_frequency != frequency)
        radio->active = -1;
    radio->cached_frequency = frequency;
    ++radio->ordinary_writes;
    return 0;
}
static int fake_read_frequency(void *context, void *opaque, uint64_t *frequency)
{
    struct fake_radio *radio = context;
    assert(opaque == radio);
    *frequency = radio->settings.center_frequency_hz;
    return 0;
}
static int fake_store(void *context, void *opaque, uint32_t profile,
    uint8_t bytes[LEO_LOCAL_RADIO_PROFILE_BYTES])
{
    struct fake_radio *radio = context;
    unsigned i;
    assert(opaque == radio);
    for (i = 0; i < LEO_LOCAL_RADIO_PROFILE_BYTES; ++i)
        radio->slots[profile][i] = (uint8_t)(profile * 29U + i + 1U);
    memcpy(bytes, radio->slots[profile], LEO_LOCAL_RADIO_PROFILE_BYTES);
    return 0;
}
static int fake_save(void *context, void *opaque, uint32_t profile,
    uint8_t bytes[LEO_LOCAL_RADIO_PROFILE_BYTES])
{
    struct fake_radio *radio = context;
    assert(opaque == radio);
    memcpy(bytes, radio->slots[profile], LEO_LOCAL_RADIO_PROFILE_BYTES);
    return 0;
}
static int fake_load(void *context, void *opaque, uint32_t profile,
    const uint8_t bytes[LEO_LOCAL_RADIO_PROFILE_BYTES])
{
    struct fake_radio *radio = context;
    assert(opaque == radio);
    memcpy(radio->slots[profile], bytes, LEO_LOCAL_RADIO_PROFILE_BYTES);
    ++radio->loads;
    return 0;
}
static int fake_recall(void *context, void *opaque, uint32_t profile)
{
    struct fake_radio *radio = context;
    assert(opaque == radio);
    if (radio->fail_recall && radio->recalls == radio->fail_recall)
        return -EIO;
    radio->active = (int32_t)profile;
    radio->slots[profile][15] ^= 0x55U; /* hardware ALC adaptation */
    ++radio->recalls;
    return 0;
}

static leo_local_radio_prepare_ops fake_ops(struct fake_radio *radio)
{
    const leo_local_radio_prepare_ops value = {
        radio, fake_open, fake_close, fake_read, fake_configure, fake_restore,
        fake_get_buffers, fake_set_buffers, fake_active, fake_write_frequency,
        fake_read_frequency, fake_store, fake_save, fake_load, fake_recall
    };
    return value;
}

static leo_local_radio_prepare_config config(void)
{
    leo_local_radio_prepare_config value;
    memset(&value, 0, sizeof(value));
    value.abi_version = LEO_LOCAL_RADIO_PREPARE_ABI_VERSION;
    value.sample_rate_hz = 2500000U;
    value.analog_bandwidth_hz = 2500000U;
    value.receiver_count = 2U;
    value.manual_gain_millidb = 40000;
    value.target_count = 2U;
    value.targets[0].profile = 0U;
    value.targets[0].frequency_hz = UINT64_C(2400000000);
    value.targets[1].profile = 3U;
    value.targets[1].frequency_hz = UINT64_C(2402000000);
    return value;
}

static void test_prepare_and_restore(void)
{
    struct fake_radio fake = {0};
    leo_local_radio_prepare_ops ops;
    leo_local_radio_prepare_config request = config();
    leo_local_radio_prepare_receipt prepared;
    leo_local_radio_restore_receipt restored;
    leo_local_radio_preparation *handle = NULL;
    leo_local_radio_settings original;
    initial_settings(&fake.settings);
    original = fake.settings;
    fake.kernel_buffers = 4U;
    fake.active = -1;
    fake.cached_frequency = fake.settings.center_frequency_hz;
    ops = fake_ops(&fake);

    assert(leo_local_radio_prepare_owned(&request, &ops,
        (leo_local_owner *)&fake, &handle, &prepared) == 0);
    assert(handle != NULL);
    assert(prepared.target_count == 2U);
    assert(prepared.targets[0].profile == 0U);
    assert(prepared.targets[0].profile_crc32 != 0U);
    assert(prepared.targets[1].profile_crc32 != 0U);
    assert(fake.kernel_buffers == LEO_LOCAL_RADIO_KERNEL_BUFFERS);
    assert(fake.active == -1);
    assert(fake.loads == 4); /* reload before and after recall proof */
    assert(fake.recalls == 4);
    assert(fake.ordinary_writes == 5); /* compile 2, exit, forced last->first */
    assert(!memcmp(fake.slots[0], prepared.targets[0].profile_bytes, 16U));
    assert(!memcmp(fake.slots[3], prepared.targets[1].profile_bytes, 16U));

    assert(leo_local_radio_restore(&handle, (leo_local_owner *)&fake, &restored) == 0);
    assert(handle == NULL);
    assert(restored.fastlock_inactive == 1U);
    assert(restored.observed_kernel_buffers == 4U);
    assert(!memcmp(&fake.settings, &original, sizeof(original)));
    assert(fake.opens == 2 && fake.closes == 2);
}

static void test_single_profile_cached_lo_exit(void)
{
    struct fake_radio fake = {0};
    leo_local_radio_prepare_ops ops;
    leo_local_radio_prepare_config request = config();
    leo_local_radio_prepare_receipt prepared;
    leo_local_radio_restore_receipt restored;
    leo_local_radio_preparation *handle = NULL;
    request.target_count = 1U;
    initial_settings(&fake.settings);
    fake.kernel_buffers = 4U;
    fake.active = -1;
    fake.cached_frequency = fake.settings.center_frequency_hz;
    ops = fake_ops(&fake);
    assert(leo_local_radio_prepare_owned(&request, &ops,
        (leo_local_owner *)&fake, &handle, &prepared) == 0);
    assert(handle && prepared.target_count == 1U);
    assert(prepared.targets[0].profile_crc32 != 0U);
    assert(fake.active == -1);
    assert(fake.ordinary_writes == 5); /* compile plus two distinct->target exits */
    assert(leo_local_radio_restore(&handle, (leo_local_owner *)&fake,
        &restored) == 0);
}

static void test_failure_restores(void)
{
    struct fake_radio fake = {0};
    leo_local_radio_prepare_ops ops;
    leo_local_radio_prepare_config request = config();
    leo_local_radio_prepare_receipt prepared;
    leo_local_radio_preparation *handle = NULL;
    leo_local_radio_settings original;
    initial_settings(&fake.settings);
    original = fake.settings;
    fake.kernel_buffers = 6U;
    fake.active = -1;
    fake.cached_frequency = fake.settings.center_frequency_hz;
    fake.fail_recall = 1;
    ops = fake_ops(&fake);

    assert(leo_local_radio_prepare_owned(&request, &ops,
        (leo_local_owner *)&fake, &handle, &prepared) == -EIO);
    assert(handle == NULL);
    assert(prepared.original.center_frequency_hz == original.center_frequency_hz);
    assert(prepared.original_kernel_buffers == 6U);
    assert(prepared.configured.sample_rate_hz == request.sample_rate_hz);
    assert(prepared.configured.receiver_mask == 3U);
    assert(prepared.cleanup_attempted == 1U);
    assert(prepared.cleanup_status == 0);
    assert(prepared.cleanup_observed_kernel_buffers == 6U);
    assert(prepared.cleanup_fastlock_inactive == 1U);
    assert(prepared.cleanup_observed.center_frequency_hz ==
        original.center_frequency_hz);
    assert(fake.kernel_buffers == 6U);
    assert(fake.active == -1);
    assert(!memcmp(&fake.settings, &original, sizeof(original)));
    assert(fake.opens == 1 && fake.closes == 1);
}

static void test_rejects_active_and_duplicate(void)
{
    struct fake_radio fake = {0};
    leo_local_radio_prepare_ops ops;
    leo_local_radio_prepare_config request = config();
    leo_local_radio_prepare_receipt receipt;
    leo_local_radio_preparation *handle = NULL;
    initial_settings(&fake.settings);
    fake.kernel_buffers = 4U;
    fake.active = 0;
    ops = fake_ops(&fake);
    assert(leo_local_radio_prepare_owned(&request, &ops,
        (leo_local_owner *)&fake, &handle, &receipt) == -EBUSY);
    assert(fake.active == 0); /* observation of another owner is non-mutating */
    request.targets[1].profile = 0U;
    assert(leo_local_radio_prepare_owned(&request, &ops,
        (leo_local_owner *)&fake, &handle, &receipt) == -EINVAL);
}

static void test_preflight_and_generic_gain_attestation(void)
{
    struct fake_radio fake = {0};
    leo_local_radio_prepare_ops ops;
    leo_local_radio_prepare_config request = config();
    leo_local_radio_prepare_receipt receipt;
    leo_local_radio_preparation *handle = NULL;
    initial_settings(&fake.settings);
    fake.kernel_buffers = 4U;
    fake.active = 0;
    ops = fake_ops(&fake);
    assert(leo_local_radio_preflight_inactive(&ops) == -EBUSY);
    assert(fake.opens == 1 && fake.closes == 1 && fake.active == 0);
    fake.active = -1;
    assert(leo_local_radio_preflight_inactive(&ops) == 0);
    fake.lie_gain = 1;
    assert(leo_local_radio_prepare_owned(&request, &ops,
        (leo_local_owner *)&fake, &handle, &receipt) == -EPROTO);
    assert(handle == NULL);
}

int main(void)
{
    test_prepare_and_restore();
    test_single_profile_cached_lo_exit();
    test_failure_restores();
    test_rejects_active_and_duplicate();
    test_preflight_and_generic_gain_attestation();
    puts("local radio preparation tests passed");
    return 0;
}
