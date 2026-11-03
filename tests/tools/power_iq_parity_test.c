#define POWER_PARITY_TEST
#include "../../tools/native_power_iq_parity.c"
#include <assert.h>

enum mode { GOOD, LATE, TIMEOUT, WRONG_ID, CLIPPED, CANCEL, CLEANUP_STUCK, FAULT, WRONG_DESCRIPTOR };
struct fake { uint32_t regs[256];uint64_t now;unsigned writes;enum mode mode;bool committed; };
static uint32_t read_fake(void *context,uint32_t offset) { return ((struct fake *)context)->regs[offset/4]; }
static void write_fake(void *context,uint32_t offset,uint32_t value)
{
 struct fake *f=context;unsigned i;uint64_t start;
 ++f->writes;f->regs[offset/4]=value;
 if(offset!=PWR_REG_COMMAND) return;
 if(value==PWR_CMD_SNAPSHOT_COUNTER) return;
 if(value==PWR_CMD_COMMIT) {
  f->committed=true;
  start=pair(f->regs[PWR_REG_START_LO/4],f->regs[PWR_REG_START_HI/4]);
  f->regs[PWR_REG_ACK_COUNTER_LO/4]=(uint32_t)(start-(f->mode==LATE?0:10));
  f->regs[PWR_REG_ACK_COUNTER_HI/4]=(uint32_t)((start-(f->mode==LATE?0:10))>>32);
  if(f->mode==TIMEOUT || f->mode==CANCEL) { f->regs[PWR_REG_STATUS/4]=PWR_STATUS_BUSY;return; }
  if(f->mode==FAULT) { f->regs[PWR_REG_STATUS/4]=PWR_STATUS_FAULT|PWR_STATUS_BUSY;return; }
  f->regs[PWR_REG_STATUS/4]=PWR_STATUS_RESULT_VALID;
  f->regs[PWR_REG_RESULT_BASE/4]=f->mode==WRONG_ID?0:PWR_IDENTITY;
  f->regs[PWR_REG_RESULT_BASE/4+1]=PWR_ABI;
  f->regs[PWR_REG_RESULT_BASE/4+2]=f->mode==CLIPPED?PWR_FLAG_CLIPPED:0;
  f->regs[PWR_REG_RESULT_BASE/4+3]=50000;
  f->regs[PWR_REG_RESULT_BASE/4+4]=f->regs[PWR_REG_SESSION/4];
  f->regs[PWR_REG_RESULT_BASE/4+5]=f->regs[PWR_REG_GENERATION/4];
  if(f->mode==WRONG_DESCRIPTOR) f->regs[PWR_REG_RESULT_BASE/4+34]=1;
  for(i=10;i<14;++i) f->regs[PWR_REG_RESULT_BASE/4+i]=
   (i==10?(uint32_t)start:i==11?(uint32_t)(start>>32):
    i==12?(uint32_t)(start+50000):(uint32_t)((start+50000)>>32));
 }
 if(value==PWR_CMD_ABORT) {
  if(f->mode==CLEANUP_STUCK) { f->regs[PWR_REG_STATUS/4]=PWR_STATUS_ABORT_PENDING;return; }
  f->regs[PWR_REG_STATUS/4]&=PWR_STATUS_RESULT_VALID|PWR_STATUS_FAULT;
  f->regs[PWR_REG_STATUS/4]|=PWR_STATUS_STOP_ACK;
 }
 if(value==PWR_CMD_POP) f->regs[PWR_REG_STATUS/4]&=~PWR_STATUS_RESULT_VALID;
 if(value==PWR_CMD_CLEAR_FAULT) f->regs[PWR_REG_STATUS/4]&=~PWR_STATUS_FAULT;
}
static uint64_t time_fake(void *context) { return ((struct fake *)context)->now; }
static void wait_fake(void *context) { ++((struct fake *)context)->now; }
static bool cancelled_fake(void *context) {
 struct fake *f=context;return f->mode==CANCEL && f->committed;
}
static struct fake fake(enum mode mode)
{
 struct fake f={.mode=mode};
 f.regs[PWR_REG_ID/4]=PWR_IDENTITY;f.regs[PWR_REG_ABI/4]=PWR_ABI;
 f.regs[PWR_REG_WINDOW_SAMPLES/4]=50000;f.regs[PWR_REG_INPUT_BITS/4]=16;
 f.regs[PWR_REG_RX_MASK/4]=3;f.regs[PWR_REG_RESULT_WORDS/4]=36;
 f.regs[PWR_REG_CAPACITY/4]=8;f.regs[PWR_REG_DATAPATH_CAPS/4]=1;
 f.regs[PWR_REG_COUNTER_LO/4]=0xfffffff0u;
 return f;
}
int main(void)
{
 struct parity_config cfg={1,2,1000000,1000,0};struct parity_result r;
 enum mode mode;
 for(mode=GOOD;mode<=WRONG_DESCRIPTOR;++mode) {
  struct fake f=fake(mode);
  struct parity_ports p={&f,read_fake,write_fake,time_fake,wait_fake,cancelled_fake};
  int ret=parity_capture(&p,&cfg,&r);
  assert(r.start>UINT32_MAX && r.snapshot==0xfffffff0u);
  assert(f.now<=1500);
  if(mode==GOOD || mode==CLIPPED) { assert(ret==0 && r.record_valid && r.cleanup_complete); }
  else if(mode==LATE) assert(ret==-ETIME && r.cleanup_complete);
  else if(mode==TIMEOUT) assert(ret==-ETIMEDOUT && r.cleanup_complete);
  else if(mode==WRONG_ID) assert(ret==-EPROTO && r.record_valid && r.cleanup_complete);
  else if(mode==CANCEL) assert(ret==-EINTR && r.cleanup_complete);
  else if(mode==CLEANUP_STUCK) assert(ret==-ETIMEDOUT && !r.cleanup_complete);
  else if(mode==FAULT) assert(ret==-EIO && r.cleanup_complete);
  else if(mode==WRONG_DESCRIPTOR) assert(ret==-EPROTO && r.record_valid && r.cleanup_complete);
 }
 {
  struct fake f=fake(GOOD);struct parity_ports p={&f,read_fake,write_fake,time_fake,wait_fake,cancelled_fake};
  f.regs[PWR_REG_STATUS/4]=PWR_STATUS_BUSY;
  assert(parity_capture(&p,&cfg,&r)==-EBUSY && f.writes==0);
  f.regs[PWR_REG_STATUS/4]=0;f.regs[PWR_REG_DATAPATH_CAPS/4]=0;
  assert(parity_capture(&p,&cfg,&r)==-EPROTONOSUPPORT && f.writes==0);
 }
 puts("PWR1 validation-only admission/ACK/timeout/cancel/raw-retention/cleanup/wrap passed");
 return 0;
}
