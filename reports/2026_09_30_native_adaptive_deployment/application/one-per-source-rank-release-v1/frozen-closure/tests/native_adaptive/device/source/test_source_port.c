#include "source_port.h"

#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <string.h>

struct fake_source {
    leo_source_capabilities capabilities;
    int16_t iq[32];
    uint64_t coordinate;
    uintptr_t token;
    int capabilities_status;
    int position_status;
    int select_status;
    int next_status;
    int release_failures;
    int malformed_block;
    int omit_boundary;
    int block_next;
    int next_waiting;
    int cancelled;
    pthread_mutex_t mutex;
    pthread_cond_t changed;
    unsigned releases;
    unsigned cancels;
};

static leo_source_capabilities exact_capabilities(void)
{
    leo_source_capabilities result;

    memset(&result, 0, sizeof(result));
    result.abi_version = LEO_SOURCE_PORT_ABI_VERSION;
    result.sample_format = LEO_SOURCE_SAMPLE_FORMAT_CI16;
    result.flags = LEO_SOURCE_CAP_CANCEL | LEO_SOURCE_CAP_SELECT |
        LEO_SOURCE_CAP_SIMULTANEOUS_RX | LEO_SOURCE_CAP_COHERENT_RX |
        LEO_SOURCE_CAP_FREQUENCY_ATTESTATION |
        LEO_SOURCE_CAP_TARGET_ATTESTATION |
        LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION |
        LEO_SOURCE_CAP_EXACT_GAP |
        LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;
    result.sample_rate_hz = 2500000U;
    result.receiver_count = 2U;
    result.maximum_samples_per_block = 8U;
    result.counter_authority = LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    result.position_semantics = LEO_SOURCE_POSITION_COHERENT_CURRENT;
    return result;
}

static int capabilities(void *opaque, leo_source_capabilities *out)
{
    struct fake_source *fake = opaque;

    *out = fake->capabilities;
    return fake->capabilities_status;
}

static int position(void *opaque, leo_source_position *out)
{
    struct fake_source *fake = opaque;

    out->coordinate = fake->coordinate;
    out->counter_authority = fake->capabilities.counter_authority;
    out->semantics = fake->capabilities.position_semantics;
    return fake->position_status;
}

static int select_source(void *opaque, const leo_source_selection *selection,
    leo_source_transition *out)
{
    struct fake_source *fake = opaque;

    if (fake->select_status)
        return fake->select_status;
    memset(out, 0, sizeof(*out));
    out->flags = LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
        LEO_SOURCE_TRANSITION_TARGET_ATTESTED |
        LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED;
    if (!fake->omit_boundary)
        out->flags |= LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;
    out->selected_target_key = selection->target_key;
    out->profile_crc32 = 17U;
    out->counter_authority = fake->omit_boundary ? 0U :
        fake->capabilities.counter_authority;
    out->position_semantics = fake->omit_boundary ? 0U :
        fake->capabilities.position_semantics;
    out->actual_frequency_hz = selection->requested_frequency_hz + 1U;
    out->previous_valid_end = fake->omit_boundary ? 0U : fake->coordinate;
    out->valid_start = fake->omit_boundary ? 0U : fake->coordinate + 2U;
    fake->coordinate += 2U;
    return 0;
}

static int next_block(void *opaque, leo_source_block *out)
{
    struct fake_source *fake = opaque;

    if (fake->block_next) {
        assert(pthread_mutex_lock(&fake->mutex) == 0);
        fake->next_waiting = 1;
        assert(pthread_cond_broadcast(&fake->changed) == 0);
        while (!fake->cancelled)
            assert(pthread_cond_wait(&fake->changed, &fake->mutex) == 0);
        assert(pthread_mutex_unlock(&fake->mutex) == 0);
        return -ECANCELED;
    }
    if (fake->next_status)
        return fake->next_status;
    memset(out, 0, sizeof(*out));
    out->ci16 = fake->iq;
    out->iq_bytes = fake->malformed_block ? sizeof(fake->iq) - 2U :
        sizeof(fake->iq);
    out->samples_per_receiver = 8U;
    out->receiver_count = 2U;
    out->flags = LEO_SOURCE_BLOCK_GAP_EXACT;
    out->counter_authority = LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    out->first_coordinate = fake->coordinate;
    out->end_coordinate = fake->coordinate + 8U;
    out->buffer_sequence = 1U;
    out->lease_token = ++fake->token;
    return 0;
}

static int release_block(void *opaque, leo_source_block *block)
{
    struct fake_source *fake = opaque;

    assert(block->lease_token == fake->token);
    ++fake->releases;
    if (fake->release_failures) {
        --fake->release_failures;
        return -EIO;
    }
    return 0;
}

static int cancel(void *opaque)
{
    struct fake_source *fake = opaque;

    ++fake->cancels;
    if (fake->block_next) {
        assert(pthread_mutex_lock(&fake->mutex) == 0);
        fake->cancelled = 1;
        assert(pthread_cond_broadcast(&fake->changed) == 0);
        assert(pthread_mutex_unlock(&fake->mutex) == 0);
    }
    return 0;
}

static const leo_source_ops operations = {
    .capabilities = capabilities,
    .position = position,
    .select = select_source,
    .next = next_block,
    .release = release_block,
    .cancel = cancel,
};

static struct fake_source exact_fake(void)
{
    struct fake_source result;

    memset(&result, 0, sizeof(result));
    result.capabilities = exact_capabilities();
    result.coordinate = 1000U;
    return result;
}

static void test_exact_lifecycle_and_clip(void)
{
    struct fake_source fake = exact_fake();
    leo_source_port port;
    leo_source_position current;
    leo_source_selection selection = {
        .target_key = 3U,
        .requested_frequency_hz = UINT64_C(2400000000),
        .maximum_frequency_error_hz = 2U,
    };
    leo_source_transition transition;
    leo_source_block block;
    leo_source_slice slice;

    assert(leo_source_port_init(&port, &fake, &operations) == 0);
    assert(leo_source_port_position(&port, &current) == 0);
    assert(current.coordinate == 1000U);
    assert(leo_source_port_select(&port, &selection, &transition) == 0);
    assert(transition.selected_target_key == 3U);
    assert(transition.profile_crc32 == 17U);
    assert(transition.previous_valid_end == 1000U);
    assert(transition.valid_start == 1002U);
    assert(leo_source_port_next(&port, &block) == 0);
    assert(leo_source_port_position(&port, &current) == -EBUSY);
    assert(leo_source_port_cancel(&port) == 0);
    assert(fake.cancels == 1U && port.outstanding_lease == block.lease_token);
    assert(leo_source_block_clip(&block, 1004U, 1008U, &slice) == 0);
    assert(slice.first_coordinate == 1004U);
    assert(slice.sample_offset == 2U);
    assert(slice.samples_per_receiver == 4U);
    assert(slice.iq_bytes == 4U * 2U * 4U);
    assert((const unsigned char *)slice.ci16 ==
        (const unsigned char *)block.ci16 + 2U * 2U * 4U);
    assert(leo_source_port_release(&port, &block) == 0);
    assert(!block.lease_token && fake.releases == 1U);
}

static void test_capability_and_status_validation(void)
{
    struct fake_source fake = exact_fake();
    leo_source_port port;

    fake.capabilities_status = 1;
    assert(leo_source_port_init(&port, &fake, &operations) == -EIO);
    fake.capabilities_status = 0;
    fake.capabilities.counter_authority =
        LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    assert(leo_source_port_init(&port, &fake, &operations) == -EPROTO);
}

static void test_missing_boundary_poisoned_after_select(void)
{
    struct fake_source fake = exact_fake();
    leo_source_port port;
    leo_source_selection selection = {
        .target_key = 1U, .requested_frequency_hz = 100U,
        .maximum_frequency_error_hz = 2U,
    };
    leo_source_transition transition;
    leo_source_position current;

    fake.omit_boundary = 1;
    assert(leo_source_port_init(&port, &fake, &operations) == 0);
    assert(leo_source_port_select(&port, &selection, &transition) == -EPROTO);
    assert(leo_source_port_position(&port, &current) == -EPROTO);
    assert(leo_source_port_cancel(&port) == 0);
}

static void test_select_callback_error_poisoned(void)
{
    struct fake_source fake = exact_fake();
    leo_source_port port;
    leo_source_selection selection = {
        .target_key = 1U, .requested_frequency_hz = 100U,
        .maximum_frequency_error_hz = 2U,
    };
    leo_source_transition transition;
    leo_source_block block;

    /* The callback contract is not transactional: an error may follow a
     * physical retune, so later acquisition must be refused. */
    fake.select_status = -EIO;
    assert(leo_source_port_init(&port, &fake, &operations) == 0);
    assert(leo_source_port_select(&port, &selection, &transition) == -EIO);
    assert(leo_source_port_next(&port, &block) == -EIO);
    assert(fake.token == 0U);
    assert(leo_source_port_cancel(&port) == 0);
}

static void test_invalid_block_release_failure_is_retained(void)
{
    struct fake_source fake = exact_fake();
    leo_source_port port;
    leo_source_block block;

    fake.malformed_block = 1;
    fake.release_failures = 1;
    assert(leo_source_port_init(&port, &fake, &operations) == 0);
    assert(leo_source_port_next(&port, &block) == -EIO);
    assert(port.outstanding_lease == 1U && fake.releases == 1U);
    assert(leo_source_port_next(&port, &block) == -EIO);
    assert(fake.releases == 1U);
    assert(leo_source_port_cancel(&port) == 0);
    assert(port.outstanding_lease == 1U);
    assert(leo_source_port_cleanup(&port) == 0);
    assert(!port.outstanding_lease && fake.releases == 2U);
    /* Cleanup releases ownership but does not clear the protocol fault. */
    assert(leo_source_port_next(&port, &block) == -EIO);
}

static void test_unknown_gap_never_becomes_numeric(void)
{
    struct fake_source fake = exact_fake();
    leo_source_port port;
    leo_source_block block;

    fake.capabilities.counter_authority =
        LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    fake.capabilities.position_semantics =
        LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    fake.capabilities.flags &= ~(LEO_SOURCE_CAP_EXACT_GAP |
        LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION |
        LEO_SOURCE_CAP_TARGET_ATTESTATION);
    assert(leo_source_port_init(&port, &fake, &operations) == 0);
    fake.malformed_block = 0;
    /* The callback deliberately still reports exact authority: the core must
     * reject and release it rather than relabel it as software-delivered. */
    assert(leo_source_port_next(&port, &block) == -EPROTO);
    assert(fake.releases == 1U && !port.outstanding_lease);
}

struct next_thread {
    leo_source_port *port;
    leo_source_block block;
    int status;
};

static void *run_next(void *opaque)
{
    struct next_thread *thread = opaque;

    thread->status = leo_source_port_next(thread->port, &thread->block);
    return NULL;
}

static void test_cancel_races_only_provider_next(void)
{
    struct fake_source fake = exact_fake();
    leo_source_port port;
    struct next_thread call;
    pthread_t thread;

    fake.block_next = 1;
    assert(pthread_mutex_init(&fake.mutex, NULL) == 0);
    assert(pthread_cond_init(&fake.changed, NULL) == 0);
    assert(leo_source_port_init(&port, &fake, &operations) == 0);
    memset(&call, 0, sizeof(call));
    call.port = &port;
    assert(pthread_create(&thread, NULL, run_next, &call) == 0);
    assert(pthread_mutex_lock(&fake.mutex) == 0);
    while (!fake.next_waiting)
        assert(pthread_cond_wait(&fake.changed, &fake.mutex) == 0);
    assert(pthread_mutex_unlock(&fake.mutex) == 0);
    assert(!port.outstanding_lease);
    assert(leo_source_port_cancel(&port) == 0);
    assert(!port.outstanding_lease);
    assert(pthread_join(thread, NULL) == 0);
    assert(call.status == -ECANCELED && !port.outstanding_lease);
    assert(pthread_cond_destroy(&fake.changed) == 0);
    assert(pthread_mutex_destroy(&fake.mutex) == 0);
}

int main(void)
{
    test_exact_lifecycle_and_clip();
    test_capability_and_status_validation();
    test_missing_boundary_poisoned_after_select();
    test_select_callback_error_poisoned();
    test_invalid_block_release_failure_is_retained();
    test_unknown_gap_never_becomes_numeric();
    test_cancel_races_only_provider_next();
    return 0;
}
