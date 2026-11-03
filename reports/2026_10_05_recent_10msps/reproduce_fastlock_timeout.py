"""Compile the deployed kernel helper with deterministic clock/SPI mocks; no RF."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

source = Path('/home/mouse9911/gits/plutosdr-linux-issue-119/drivers/iio/adc/ad9361.c')
text = source.read_text()
start = text.index('static int ad9361_counter_wait_rx_lock(')
end = text.index('\n}\n', start) + 3
function = text[start:end]
prefix = r'''
#include <errno.h>
#include <stdio.h>
#include <assert.h>
typedef long long ktime_t;
struct ad9361_rf_phy { void *spi; };
#define REG_RX_CP_OVERRANGE_VCO_LOCK 0
#define VCO_LOCK 2
static long long now_us, read_us;
static int status_value;
static ktime_t ktime_get(void) { return now_us; }
static ktime_t ktime_add_us(ktime_t t, long long us) { return t + us; }
static int ktime_compare(ktime_t a, ktime_t b) { return (a > b) - (a < b); }
static int ad9361_spi_read(void *spi, int reg) {
    (void)spi; (void)reg; now_us += read_us; return status_value;
}
static void usleep_range(int a, int b) { (void)b; now_us += a; }
'''
main = r'''
int main(void) {
    struct ad9361_rf_phy phy = {0};
    now_us = 0; read_us = 100; status_value = VCO_LOCK;
    int fast = ad9361_counter_wait_rx_lock(&phy);
    now_us = 0; read_us = 2500; status_value = VCO_LOCK;
    int delayed_locked = ad9361_counter_wait_rx_lock(&phy);
    now_us = 0; read_us = 2500; status_value = 0;
    int unlocked = ad9361_counter_wait_rx_lock(&phy);
    now_us = 0; read_us = 100; status_value = -EIO;
    int spi_error = ad9361_counter_wait_rx_lock(&phy);
    assert(fast == 0 && delayed_locked == -ETIMEDOUT);
    assert(unlocked == -ETIMEDOUT && spi_error == -EIO);
    printf("{\"locked_100us\":%d,\"locked_2500us\":%d,"
           "\"unlocked_2500us\":%d,\"spi_error\":%d}\n",
           fast, delayed_locked, unlocked, spi_error);
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='leo-fastlock-rca-', dir='/var/tmp') as work:
    path=Path(work)
    (path/'test.c').write_text(prefix+function+main)
    subprocess.run(['cc','-Wall','-Wextra','-Werror',str(path/'test.c'),'-o',str(path/'test')],check=True)
    result=json.loads(subprocess.check_output([str(path/'test')],text=True))
result['kernel_source_commit']='d3611e575b09fa4e43be99a513423cb1ab3f4d37'
result['source_file_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
result['helper_sha256']=hashlib.sha256(function.encode()).hexdigest()
result['scope']='Exact deployed-source helper with synthetic SPI status and elapsed time; demonstrates failure mechanism, not observed per-recall status.'
(Path(__file__).parent/'fastlock-reproduction.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
