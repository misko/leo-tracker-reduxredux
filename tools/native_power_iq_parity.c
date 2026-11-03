/* SPDX-License-Identifier: BSD-1-Clause
 * Validation-only PWR1 arm beside one existing native DMA owner. No RF ioctl,
 * scan owner acquisition, LO/gain write, IQ OPEN, or daemon is performed.
 * Compile with the reviewed PWR1 power_scanner_regs.h include directory.
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../native/power_scanner/power_scanner_regs.h"

struct parity_ports {
 void *context;
 uint32_t (*read)(void *, uint32_t);
 void (*write)(void *, uint32_t, uint32_t);
 uint64_t (*now_ms)(void *);
 void (*wait)(void *);
 bool (*cancelled)(void *);
};
struct parity_config { uint32_t session, generation, future_samples, timeout_ms, adc12; };
struct parity_result {
 uint64_t snapshot, start;
 uint32_t caps, words[PWR_RESULT_WORDS];
 bool record_valid, cleanup_complete;
 int error, cleanup_error;
};
static uint64_t pair(uint32_t low, uint32_t high) { return low | (uint64_t)high<<32; }
static int poll_status(const struct parity_ports *p, uint32_t absent, uint32_t present,
                       uint64_t deadline, bool cancellable)
{
 for (;;) {
  uint32_t status=p->read(p->context,PWR_REG_STATUS);
  if(cancellable && (status&PWR_STATUS_FAULT)) return -EIO;
  if (!(status & absent) && (status & present)==present) return 0;
  if (cancellable && p->cancelled(p->context)) return -EINTR;
  if (p->now_ms(p->context)>=deadline) return -ETIMEDOUT;
  p->wait(p->context);
 }
}
static void read_record(const struct parity_ports *p, struct parity_result *r)
{
 unsigned i;
 for(i=0;i<PWR_RESULT_WORDS;++i) r->words[i]=p->read(p->context,PWR_REG_RESULT_BASE+4*i);
 r->record_valid=true;
}
static int parity_capture(const struct parity_ports *p, const struct parity_config *cfg,
                          struct parity_result *r)
{
 uint32_t status, shadow[12]={0};
 uint64_t deadline;
 unsigned i;
 int ret;
 bool committed=false;
 memset(r,0,sizeof(*r));
 if (!cfg->session || !cfg->generation || cfg->future_samples<125000 ||
     cfg->future_samples>2500000 || cfg->timeout_ms<200 || cfg->timeout_ms>10000 || cfg->adc12>1)
  return r->error=-EINVAL;
 r->caps=p->read(p->context,PWR_REG_DATAPATH_CAPS);
 if(p->read(p->context,PWR_REG_ID)!=PWR_IDENTITY || p->read(p->context,PWR_REG_ABI)!=PWR_ABI ||
    p->read(p->context,PWR_REG_WINDOW_SAMPLES)!=50000 ||
    p->read(p->context,PWR_REG_INPUT_BITS)!=16 || p->read(p->context,PWR_REG_RX_MASK)!=3 ||
    p->read(p->context,PWR_REG_RESULT_WORDS)!=36 || p->read(p->context,PWR_REG_CAPACITY)<1 ||
    !(r->caps&PWR_CAP_NATIVE_FACTOR1) || (r->caps&~3u)) return r->error=-EPROTONOSUPPORT;
 status=p->read(p->context,PWR_REG_STATUS);
 if(status & ~PWR_STATUS_STOP_ACK) return r->error=-EBUSY;
 deadline=p->now_ms(p->context)+cfg->timeout_ms;
 p->write(p->context,PWR_REG_COMMAND,PWR_CMD_SNAPSHOT_COUNTER);
 ret=poll_status(p,PWR_STATUS_COUNTER_PENDING,0,deadline,true);
 if(ret) return r->error=ret;
 r->snapshot=pair(p->read(p->context,PWR_REG_COUNTER_LO),p->read(p->context,PWR_REG_COUNTER_HI));
 if(r->snapshot>UINT64_MAX-cfg->future_samples-50000u) return r->error=-EOVERFLOW;
 r->start=r->snapshot+cfg->future_samples;
 shadow[0]=(uint32_t)r->start; shadow[1]=(uint32_t)(r->start>>32); shadow[2]=50000;
 shadow[3]=cfg->session; shadow[4]=cfg->generation; shadow[11]=cfg->adc12;
 for(i=0;i<12;++i) p->write(p->context,PWR_REG_START_LO+4*i,shadow[i]);
 p->write(p->context,PWR_REG_COMMAND,PWR_CMD_COMMIT); committed=true;
 ret=poll_status(p,PWR_STATUS_COMMAND_PENDING,0,deadline,true);
 if(ret) goto cleanup;
 if(p->read(p->context,PWR_REG_ACK_CODE) || p->read(p->context,PWR_REG_ACK_VISIT) ||
    pair(p->read(p->context,PWR_REG_ACK_COUNTER_LO),p->read(p->context,PWR_REG_ACK_COUNTER_HI))>=r->start)
  { ret=-ETIME; goto cleanup; }
 ret=poll_status(p,0,PWR_STATUS_RESULT_VALID,deadline,true);
 if(ret) goto cleanup;
 read_record(p,r);
 if(r->words[0]!=PWR_IDENTITY || r->words[1]!=PWR_ABI || r->words[3]!=50000 ||
    r->words[4]!=cfg->session || r->words[5]!=cfg->generation || r->words[2]&~PWR_FLAG_CLIPPED ||
    r->words[6] || r->words[7] || r->words[8] || r->words[9] || r->words[34] || r->words[35] ||
    pair(r->words[10],r->words[11])!=r->start || pair(r->words[12],r->words[13])!=r->start+50000u)
  ret=-EPROTO;
cleanup:
 r->error=ret;
 if(committed) {
  deadline=p->now_ms(p->context)+500;
  p->write(p->context,PWR_REG_COMMAND,PWR_CMD_ABORT);
  r->cleanup_error=poll_status(p,PWR_STATUS_ABORT_PENDING,PWR_STATUS_STOP_ACK,deadline,false);
  if(!r->cleanup_error && p->read(p->context,PWR_REG_STATUS)&PWR_STATUS_RESULT_VALID) {
   if(!r->record_valid) read_record(p,r);
   p->write(p->context,PWR_REG_COMMAND,PWR_CMD_POP);
   r->cleanup_error=poll_status(p,PWR_STATUS_RESULT_VALID|PWR_STATUS_POP_PENDING,0,deadline,false);
  }
  if(!r->cleanup_error && p->read(p->context,PWR_REG_STATUS)&PWR_STATUS_FAULT)
   p->write(p->context,PWR_REG_COMMAND,PWR_CMD_CLEAR_FAULT);
  if(!r->cleanup_error)
   r->cleanup_error=poll_status(p,~PWR_STATUS_STOP_ACK,0,deadline,false);
  r->cleanup_complete=!r->cleanup_error;
  if(!r->cleanup_complete && !r->cleanup_error) r->cleanup_error=-EIO;
 }
 return r->error ? r->error : r->cleanup_error;
}

#ifndef POWER_PARITY_TEST
#include <fcntl.h>
#include <signal.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t interrupted;
struct memory { volatile uint32_t *registers; };
static void interrupt_handler(int unused) { (void)unused; interrupted=1; }
static uint32_t read_mmio(void *ctx,uint32_t offset) { return ((struct memory *)ctx)->registers[offset/4]; }
static void write_mmio(void *ctx,uint32_t offset,uint32_t value) {
 ((struct memory *)ctx)->registers[offset/4]=value;
 __sync_synchronize();
}
static uint64_t now_ms(void *ctx) {
 struct timespec t; (void)ctx; clock_gettime(CLOCK_MONOTONIC,&t);
 return (uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000;
}
static void pause_ms(void *ctx) { struct timespec delay={0,1000000};(void)ctx;nanosleep(&delay,NULL); }
static bool cancelled(void *ctx) { (void)ctx; return interrupted!=0; }
static int number(const char *text,uint32_t *value) {
 char *end; unsigned long result;
 if(!*text || *text<'0' || *text>'9') return -EINVAL;
 errno=0;result=strtoul(text,&end,10);
 if(errno || *end || result>UINT32_MAX) return -EINVAL;
 *value=(uint32_t)result;return 0;
}
int main(int argc,char **argv)
{
 int lock_fd=-1,memory_fd=-1,result=1;
 unsigned i;
 struct memory memory={0}; struct parity_result receipt={0};
 struct parity_config config={0};
 uint32_t *fields[]={&config.session,&config.generation,&config.future_samples,&config.timeout_ms,&config.adc12};
 struct parity_ports ports={&memory,read_mmio,write_mmio,now_ms,pause_ms,cancelled};
 if(argc!=6) { fprintf(stderr,"usage: %s SESSION GENERATION FUTURE_SAMPLES TIMEOUT_MS ADC12_QUALIFIED\n",argv[0]);return 2; }
 for(i=0;i<5;++i) if(number(argv[i+1],fields[i])) return 2;
 lock_fd=open("/run/leo-power-scanner.lock",O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);
 if(lock_fd<0 || flock(lock_fd,LOCK_EX|LOCK_NB)) { receipt.error=-EBUSY;goto report; }
 memory_fd=open("/dev/mem",O_RDWR|O_SYNC|O_CLOEXEC);
 if(memory_fd<0) { receipt.error=-errno;goto report; }
 memory.registers=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,memory_fd,0x7c460000u);
 if(memory.registers==MAP_FAILED) { memory.registers=NULL;receipt.error=-errno;goto report; }
 signal(SIGINT,interrupt_handler);signal(SIGTERM,interrupt_handler);
 result=parity_capture(&ports,&config,&receipt) ? 1 : 0;
report:
 printf("{\"schema\":\"leo.power-iq-parity-mmio.v1\",\"session\":%u,\"generation\":%u,"
        "\"snapshot\":%" PRIu64 ",\"start\":%" PRIu64 ",\"datapath_caps\":%u,"
        "\"error\":%d,\"cleanup_error\":%d,\"cleanup_complete\":%s,\"record_valid\":%s,"
        "\"radio_acquired\":false,\"words\":[",
        config.session,config.generation,receipt.snapshot,receipt.start,receipt.caps,receipt.error,
        receipt.cleanup_error,receipt.cleanup_complete?"true":"false",receipt.record_valid?"true":"false");
 for(i=0;i<36;++i) printf("%s%u",i?",":"",receipt.words[i]);
 puts("]}");
 if(memory.registers) munmap((void *)memory.registers,4096);
 if(memory_fd>=0) close(memory_fd);
 if(lock_fd>=0) close(lock_fd);
 return result;
}
#endif
