#include "local_source.h"
#include "local_source_port.h"
#include "vendor/adi-rx-counter.h"

#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define SAMPLES 100U
#define RAW_BYTES (8U + SAMPLES * 4U)

struct fake_block {
    uint8_t raw[RAW_BYTES];
    size_t bytes;
};

struct fake_device {
    struct fake_block blocks[4];
    unsigned block_count;
    unsigned next_block;
    unsigned releases;
    unsigned release_failures;
    uintptr_t last_released;
    uint32_t snapshot_low;
    uint64_t profile_frequency[8];
    uint32_t profile_crc[8];
    uint32_t recall_crc_override;
    int recall_crc_override_valid;
    uint64_t restored_frequency;
    int capture_open;
    int counter_open;
    int radio_owned;
};

static struct fake_device *active;

static void put64(void *destination, uint64_t value)
{
    uint8_t *p = destination;
    unsigned i;

    for (i = 0; i < 8; ++i)
        p[i] = (uint8_t)(value >> (8U * i));
}

static void add_block(struct fake_device *device, uint64_t first)
{
    struct fake_block *block = &device->blocks[device->block_count++];
    unsigned i;

    memset(block, 0, sizeof(*block));
    put64(block->raw, first + 2U);
    for (i = 8; i < RAW_BYTES; ++i)
        block->raw[i] = (uint8_t)i;
    block->bytes = RAW_BYTES;
}

static int fake_capture_open(void *context, const struct leo_local_config *config,
    void **capture)
{
    struct fake_device *device = context;

    assert(config->sample_rate_hz == 2500000U);
    assert(config->analog_bandwidth_hz == 2500000U);
    assert(config->samples_per_block == SAMPLES);
    assert(config->receiver_count == 1U);
    assert(config->kernel_buffer_count == 4U);
    if (device->capture_open)
        return -EBUSY;
    device->capture_open = 1;
    *capture = device;
    return 0;
}

static int fake_capture_acquire(void *context, void *capture,
    struct leo_local_provider_block *block)
{
    struct fake_device *device = context;
    struct fake_block *source;

    assert(capture == device);
    if (device->next_block >= device->block_count)
        return -ENODEV;
    source = &device->blocks[device->next_block];
    block->raw = source->raw;
    block->raw_bytes = source->bytes;
    block->token = ++device->next_block;
    return 0;
}

static int fake_capture_release(void *context, void *capture, uintptr_t token)
{
    struct fake_device *device = context;

    assert(capture == device);
    assert(token && token <= device->next_block);
    if (device->release_failures) {
        --device->release_failures;
        return -EIO;
    }
    ++device->releases;
    device->last_released = token;
    return 0;
}

static int fake_capture_cancel(void *context, void *capture)
{
    assert(context == capture);
    return 0;
}

static int fake_capture_close(void *context, void *capture)
{
    struct fake_device *device = context;

    assert(capture == device);
    assert(device->capture_open);
    device->capture_open = 0;
    return 0;
}

static int fake_counter_open(void)
{
    assert(active);
    ++active->counter_open;
    return 42 + active->counter_open;
}

static int fake_counter_close(int fd)
{
    assert(active && fd >= 43);
    --active->counter_open;
    return 0;
}

static int fake_ioctl(int fd, unsigned long request, void *argument)
{
    (void)fd;
    assert(active);
    if (request == ADI_RX_COUNTER_IOC_GET_SCAN_CAPS) {
        struct adi_rx_counter_scan_caps *caps = argument;

        caps->magic = ADI_RX_COUNTER_MAGIC;
        caps->version = ADI_RX_COUNTER_SCAN_VERSION;
        caps->size = sizeof(*caps);
        caps->features = ADI_RX_COUNTER_SCAN_FEATURES;
        caps->maximum_profiles = ADI_RX_COUNTER_SCAN_MAX_PROFILES;
        caps->source_counter_bits = 32;
        caps->frequency_resolution_hz = 2;
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_ACQUIRE) {
        struct adi_rx_counter_request *acquire = argument;

        assert(acquire->magic == ADI_RX_COUNTER_MAGIC);
        assert(acquire->sample_rate_hz == 2500000U);
        assert(acquire->samples_per_channel == SAMPLES);
        if (active->radio_owned) {
            errno = EBUSY;
            return -1;
        }
        active->radio_owned = 1;
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_CONFIGURE_SCAN) {
        struct adi_rx_counter_scan_config *config = argument;
        unsigned i;

        for (i = 0; i < 8; ++i) {
            active->profile_frequency[i] = config->profiles[i].frequency_hz;
            active->profile_crc[i] = config->profiles[i].crc32;
        }
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_SCAN_SNAPSHOT) {
        struct adi_rx_counter_scan_snapshot *snapshot = argument;

        snapshot->counter = active->snapshot_low;
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_RECALL) {
        struct adi_rx_counter_scan_recall *recall = argument;

        recall->frequency_hz = active->profile_frequency[recall->profile];
        recall->profile_crc32 = active->recall_crc_override_valid ?
            active->recall_crc_override : active->profile_crc[recall->profile];
        recall->counter_before = UINT32_C(0xfffffff0);
        recall->counter_after = UINT32_C(0x00000010);
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_RELEASE_SCAN) {
        struct adi_rx_counter_scan_release *release = argument;

        release->frequency_hz = active->restored_frequency;
        release->counter_before = UINT32_C(0x00000100);
        release->counter_after = UINT32_C(0x00000110);
        active->radio_owned = 0;
        return 0;
    }
    errno = ENOTTY;
    return -1;
}

static struct leo_local_provider_ops provider(struct fake_device *device)
{
    struct leo_local_provider_ops result = {
        .context = device,
        .capture_open = fake_capture_open,
        .capture_acquire = fake_capture_acquire,
        .capture_cancel = fake_capture_cancel,
        .capture_release = fake_capture_release,
        .capture_close = fake_capture_close,
        .counter_open = fake_counter_open,
        .counter_close = fake_counter_close,
        .ioctl_call = fake_ioctl,
    };

    active = device;
    return result;
}

static struct leo_local_config config(void)
{
    struct leo_local_config result = {
        .sample_rate_hz = 2500000U,
        .analog_bandwidth_hz = 2500000U,
        .samples_per_block = SAMPLES,
        .receiver_count = 1U,
        .kernel_buffer_count = 4U,
        .profile_count = 2U,
    };

    result.profiles[0] = (struct leo_local_profile) {
        .profile = 0, .frequency_hz = UINT64_C(10700000000), .crc32 = 11
    };
    result.profiles[1] = (struct leo_local_profile) {
        .profile = 1, .frequency_hz = UINT64_C(11200000000), .crc32 = 22
    };
    return result;
}

static void test_lifecycle_rollover_gap_clip_and_exclusive_owner(void)
{
    const uint64_t first = UINT64_C(0xffffff00);
    struct fake_device device = { 0 };
    struct leo_local_provider_ops ops;
    struct leo_local_config setup = config();
    struct leo_local_prime_receipt prime;
    struct leo_local_transition transition;
    struct leo_local_restore_receipt restore;
    struct leo_local_block block, second_block;
    struct leo_local_slice slice;
    struct leo_local_source *source, *other;
    uint64_t snapshot;

    device.snapshot_low = UINT32_C(0xffffff80);
    device.restored_frequency = UINT64_C(10500000000);
    device.recall_crc_override = 33;
    device.recall_crc_override_valid = 1;
    add_block(&device, first);
    add_block(&device, first + 200U); /* one complete missing block */
    ops = provider(&device);
    assert(leo_local_source_open(&setup, &ops, &source) == 0);
    {
        struct leo_local_config described;
        memset(&described, 0, sizeof(described));
        assert(leo_local_source_describe(source, &described) == 0);
        assert(memcmp(&described, &setup, sizeof(setup)) == 0);
        assert(leo_local_source_describe(NULL, &described) == -EINVAL);
        assert(leo_local_source_describe(source, NULL) == -EINVAL);
    }
    assert(leo_local_source_open(&setup, &ops, &other) == -EBUSY);
    assert(leo_local_source_prime(source, &prime) == 0);
    assert(prime.discarded_first_counter == first);
    assert(prime.discarded_end_counter == first + SAMPLES);
    assert(prime.coherent_counter == UINT64_C(0xffffff80));
    assert(device.releases == 1);
    assert(leo_local_source_recall(source, 1, &transition) == 0);
    assert(transition.frequency_hz == setup.profiles[1].frequency_hz);
    assert(transition.profile_crc32 == 33);
    assert(transition.previous_valid_end == UINT64_C(0xfffffff0));
    assert(transition.valid_start == UINT64_C(0x100000010));
    assert(leo_local_source_next(source, &block) == 0);
    assert(block.first_counter == first + 200U);
    assert(block.end_counter == first + 300U);
    assert(block.missing_samples_before == 100U);
    assert(block.buffer_sequence == 2U);
    assert(leo_local_source_next(source, &second_block) == -EINVAL);
    assert(leo_local_source_recall(source, 0, &transition) == -EINVAL);
    assert(leo_local_block_clip(&block, UINT64_C(0x100000010),
        UINT64_C(0x100000100), &slice) == 0);
    assert(slice.first_counter == UINT64_C(0x100000010));
    assert(slice.sample_offset == 72U);
    assert(slice.samples_per_receiver == 28U);
    assert(slice.iq_bytes == 28U * 4U);
    assert((const uint8_t *)slice.ci16 == (const uint8_t *)block.ci16 + 72U * 4U);
    assert(leo_local_source_release(source, &block) == 0);
    assert(!block.lease_token && device.releases == 2);
    assert(leo_local_source_release(source, &block) == -EINVAL);
    device.snapshot_low = UINT32_C(0x00000080);
    assert(leo_local_source_snapshot(source, &snapshot) == 0);
    assert(snapshot == UINT64_C(0x100000080));
    assert(leo_local_source_next(source, &block) == -ENODEV);
    assert(leo_local_source_close(source, &restore) == 0);
    assert(restore.frequency_hz == device.restored_frequency);
    assert(restore.counter_before == UINT64_C(0x100000100));
    assert(restore.counter_after == UINT64_C(0x100000110));
    assert(!device.radio_owned && !device.capture_open && !device.counter_open);
}

static void test_close_releases_outstanding_block(void)
{
    struct fake_device device = { 0 };
    struct leo_local_provider_ops ops;
    struct leo_local_config setup = config();
    struct leo_local_prime_receipt prime;
    struct leo_local_transition transition;
    struct leo_local_restore_receipt restore;
    struct leo_local_block block;
    struct leo_local_source *source;

    device.snapshot_low = 1200U;
    device.restored_frequency = UINT64_C(10500000000);
    add_block(&device, 1000U);
    add_block(&device, 1100U);
    ops = provider(&device);
    assert(leo_local_source_open(&setup, &ops, &source) == 0);
    assert(leo_local_source_prime(source, &prime) == 0);
    assert(leo_local_source_recall(source, 0, &transition) == 0);
    assert(leo_local_source_next(source, &block) == 0);
    assert(device.releases == 1);
    assert(leo_local_source_close(source, &restore) == 0);
    assert(device.releases == 2);
    assert(!device.radio_owned && !device.capture_open);
}

static void test_malformed_block_is_released_and_faults_source(void)
{
    struct fake_device device = { 0 };
    struct leo_local_provider_ops ops;
    struct leo_local_config setup = config();
    struct leo_local_prime_receipt prime;
    struct leo_local_restore_receipt restore;
    struct leo_local_source *source;

    device.snapshot_low = 2000U;
    device.restored_frequency = UINT64_C(10500000000);
    add_block(&device, 1000U);
    device.blocks[0].bytes--;
    ops = provider(&device);
    assert(leo_local_source_open(&setup, &ops, &source) == 0);
    assert(leo_local_source_prime(source, &prime) == -EIO);
    assert(device.releases == 1);
    assert(leo_local_source_prime(source, &prime) == -EINVAL);
    assert(leo_local_source_close(source, &restore) == 0);
    assert(!device.radio_owned && !device.capture_open);
}

static void test_zero_recall_crc_faults_source(void)
{
    struct fake_device device = { 0 };
    struct leo_local_provider_ops ops;
    struct leo_local_config setup = config();
    struct leo_local_prime_receipt prime;
    struct leo_local_transition transition;
    struct leo_local_restore_receipt restore;
    struct leo_local_source *source;

    device.snapshot_low = 1200U;
    device.restored_frequency = UINT64_C(10500000000);
    device.recall_crc_override_valid = 1;
    device.recall_crc_override = 0;
    add_block(&device, 1000U);
    ops = provider(&device);
    assert(leo_local_source_open(&setup, &ops, &source) == 0);
    assert(leo_local_source_prime(source, &prime) == 0);
    assert(leo_local_source_recall(source, 0, &transition) == -EPROTO);
    assert(leo_local_source_recall(source, 0, &transition) == -EINVAL);
    assert(leo_local_source_close(source, &restore) == 0);
}

static void test_reservation_activation_and_restore_phase(void)
{
    struct fake_device device = { 0 };
    struct leo_local_provider_ops ops = provider(&device);
    struct leo_local_config settings = config();
    struct leo_local_restore_receipt receipt;
    struct leo_local_owner *owner = NULL, *returned = NULL;
    struct leo_local_source *source = NULL;
    device.restored_frequency = UINT64_C(915000000);

    assert(leo_local_owner_acquire(&settings, &ops, &owner) == 0);
    assert(owner != NULL && leo_local_owner_is_live(owner));
    assert(!leo_local_owner_is_active(owner));
    assert(device.counter_open == 1 && device.radio_owned == 0);
    /* Bufferless preparation occurs in this reserved, firmware-inactive phase. */
    assert(leo_local_source_open_owned(&settings, &ops, owner, &source) == 0);
    assert(leo_local_owner_is_active(owner));
    assert(device.radio_owned == 1);
    assert(leo_local_source_close_preserve_owner(source, &returned) == 0);
    assert(returned == owner && device.counter_open == 1);
    assert(leo_local_owner_deactivate(owner, 0U, &receipt) == 0);
    assert(!leo_local_owner_is_active(owner));
    assert(leo_local_owner_is_live(owner) && device.counter_open == 1);
    /* Exact IIO restoration occurs here while the reservation remains held. */
    assert(leo_local_owner_release(owner, 0U, &receipt) == 0);
    assert(device.counter_open == 0 && device.radio_owned == 0);
}

static void test_transport_neutral_port_maps_exact_local_authority(void)
{
    const uint64_t first = UINT64_C(0xffffff00);
    struct fake_device device = { 0 };
    struct leo_local_provider_ops ops;
    struct leo_local_config setup = config();
    struct leo_local_prime_receipt prime;
    struct leo_local_restore_receipt restore;
    struct leo_local_source *source;
    struct leo_local_source_port *adapter;
    struct leo_source_port *port;
    struct leo_source_capabilities capabilities;
    struct leo_source_position position;
    struct leo_source_selection selection = {
        .target_key = 1U,
        .requested_frequency_hz = UINT64_C(11200000000),
        .maximum_frequency_error_hz = 2U,
    };
    struct leo_source_transition transition;
    struct leo_source_block block;
    struct leo_source_slice slice;

    device.snapshot_low = UINT32_C(0xffffff80);
    device.restored_frequency = UINT64_C(10500000000);
    add_block(&device, first);
    add_block(&device, first + 200U);
    ops = provider(&device);
    assert(leo_local_source_open(&setup, &ops, &source) == 0);
    assert(leo_local_source_prime(source, &prime) == 0);
    assert(leo_local_source_port_create(source, &setup, &adapter) == 0);
    port = leo_local_source_port_get(adapter);
    assert(leo_source_port_capabilities(port, &capabilities) == 0);
    assert(capabilities.counter_authority ==
        LEO_SOURCE_COUNTER_PROVIDER_EXACT);
    assert(capabilities.position_semantics ==
        LEO_SOURCE_POSITION_COHERENT_CURRENT);
    assert(capabilities.receiver_count == 1U);
    assert(leo_source_port_position(port, &position) == 0);
    assert(position.coordinate == UINT64_C(0xffffff80));
    assert(leo_source_port_select(port, &selection, &transition) == 0);
    assert(transition.selected_target_key == 1U);
    assert(transition.profile_crc32 == setup.profiles[1].crc32);
    assert(transition.previous_valid_end == UINT64_C(0xfffffff0));
    assert(transition.valid_start == UINT64_C(0x100000010));
    assert(leo_source_port_next(port, &block) == 0);
    assert(block.flags & LEO_SOURCE_BLOCK_GAP_EXACT);
    assert(block.flags & LEO_SOURCE_BLOCK_DISCONTINUITY);
    assert(block.missing_samples_before == 100U);
    assert(leo_local_source_port_destroy(adapter) == -EBUSY);
    assert(leo_source_block_clip(&block, UINT64_C(0x100000010),
        UINT64_C(0x100000100), &slice) == 0);
    assert(slice.sample_offset == 72U && slice.samples_per_receiver == 28U);
    assert(leo_source_port_cancel(port) == 0);
    assert(leo_source_port_release(port, &block) == 0);
    assert(leo_local_source_port_destroy(adapter) == 0);
    assert(leo_local_source_close(source, &restore) == 0);
}

static void test_local_shape_mismatch_retains_failed_cleanup(void)
{
    struct fake_device device = { 0 };
    struct leo_local_provider_ops ops;
    struct leo_local_config setup = config();
    struct leo_local_config claimed = setup;
    struct leo_local_prime_receipt prime;
    struct leo_local_restore_receipt restore;
    struct leo_local_source *source;
    struct leo_local_source_port *adapter;
    struct leo_source_port *port;
    struct leo_source_selection selection = {
        .target_key = 0U,
        .requested_frequency_hz = UINT64_C(10700000000),
        .maximum_frequency_error_hz = 2U,
    };
    struct leo_source_transition transition;
    struct leo_source_block block;

    device.snapshot_low = 1200U;
    device.restored_frequency = UINT64_C(10500000000);
    add_block(&device, 1000U);
    add_block(&device, 1100U);
    ops = provider(&device);
    assert(leo_local_source_open(&setup, &ops, &source) == 0);
    assert(leo_local_source_prime(source, &prime) == 0);
    /* The opaque local source cannot yet attest its open config. A false copy
     * must fail closed without losing the provider lease. */
    claimed.receiver_count = 2U;
    assert(leo_local_source_port_create(source, &claimed, &adapter) == 0);
    port = leo_local_source_port_get(adapter);
    assert(leo_source_port_select(port, &selection, &transition) == 0);
    device.release_failures = 1U;
    assert(leo_source_port_next(port, &block) == -EIO);
    assert(port->outstanding_lease != 0U);
    assert(leo_local_source_port_destroy(adapter) == -EBUSY);
    assert(leo_source_port_cleanup(port) == 0);
    assert(!port->outstanding_lease);
    assert(leo_local_source_port_destroy(adapter) == 0);
    assert(leo_local_source_close(source, &restore) == 0);
}

static void test_adapter_abandon_transfers_failed_lease_to_source_close(void)
{
    struct fake_device device = { 0 };
    struct leo_local_provider_ops ops;
    struct leo_local_config setup = config();
    struct leo_local_prime_receipt prime;
    struct leo_local_restore_receipt restore;
    struct leo_local_source *source;
    struct leo_local_source_port *adapter;
    struct leo_source_port *port;
    struct leo_source_selection selection = {
        .target_key = 0U,
        .requested_frequency_hz = UINT64_C(10700000000),
        .maximum_frequency_error_hz = 2U,
    };
    struct leo_source_transition transition;
    struct leo_source_block block;

    device.snapshot_low = 1200U;
    device.restored_frequency = UINT64_C(10500000000);
    add_block(&device, 1000U);
    add_block(&device, 1100U);
    ops = provider(&device);
    assert(leo_local_source_open(&setup, &ops, &source) == 0);
    assert(leo_local_source_prime(source, &prime) == 0);
    assert(leo_local_source_port_create(source, &setup, &adapter) == 0);
    port = leo_local_source_port_get(adapter);
    assert(leo_source_port_select(port, &selection, &transition) == 0);
    assert(leo_source_port_next(port, &block) == 0);
    device.release_failures = 2U;
    assert(leo_source_port_release(port, &block) == -EIO);
    assert(leo_source_port_cleanup(port) == -EIO);
    assert(leo_local_source_port_abandon_lease(adapter) == 0);
    assert(leo_local_source_close(source, &restore) == 0);
    assert(device.last_released == 2U);
}

int main(void)
{
    test_lifecycle_rollover_gap_clip_and_exclusive_owner();
    test_malformed_block_is_released_and_faults_source();
    test_close_releases_outstanding_block();
    test_zero_recall_crc_faults_source();
    test_reservation_activation_and_restore_phase();
    test_transport_neutral_port_maps_exact_local_authority();
    test_local_shape_mismatch_retains_failed_cleanup();
    test_adapter_abandon_transfers_failed_lease_to_source_close();
    puts("local source fake-driver tests passed");
    return 0;
}
