#define _GNU_SOURCE
#include <signal.h>
#include <stdint.h>
#include <time.h>
#include <ucontext.h>

/* CPU-time diagnostic. The signal handler only stores the interrupted PC. */
#define CAPACITY 32768
static volatile sig_atomic_t active, used, overruns;
static volatile uintptr_t locations[CAPACITY];
static timer_t clock_timer;
static struct sigaction previous;

static void sample(int signum, siginfo_t *signal, void *context) {
    (void)signum;
    if (active && used < CAPACITY) {
        ucontext_t *thread = context;
        locations[used++] = (uintptr_t)thread->uc_mcontext.gregs[REG_RIP];
        overruns += signal->si_overrun;
    }
}

int start_samples(int interval_us) {
    struct sigaction action = {.sa_sigaction = sample, .sa_flags = SA_SIGINFO | SA_RESTART};
    struct sigevent event = {.sigev_notify = SIGEV_SIGNAL, .sigev_signo = SIGPROF};
    struct itimerspec periods = {{0, interval_us * 1000L}, {0, interval_us * 1000L}};
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGPROF, NULL, &previous) || previous.sa_handler != SIG_DFL ||
        sigaction(SIGPROF, &action, NULL)) {
        return -1;
    }
    used = overruns = active = 0;
    if (timer_create(CLOCK_THREAD_CPUTIME_ID, &event, &clock_timer)) {
        sigaction(SIGPROF, &previous, NULL);
        return -2;
    }
    if (timer_settime(clock_timer, 0, &periods, NULL)) {
        timer_delete(clock_timer);
        sigaction(SIGPROF, &previous, NULL);
        return -3;
    }
    return 0;
}

void mark_decode(int value) { active = value; }
int samples_size(void) { return used; }
int stop_samples(void) {
    active = 0;
    timer_delete(clock_timer);
    return used;
}
uintptr_t sample_at(int index) { return locations[index]; }
int sample_overruns(void) { return overruns; }
