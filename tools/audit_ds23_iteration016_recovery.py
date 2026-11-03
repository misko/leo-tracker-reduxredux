"""Reuse independent density, gate and measurement checks on frozen016 trials."""

from pathlib import Path
import probe_ds23_iteration016_recovery as binding
import audit_ds23_iteration014_recovery as audit
import audit_ds23_iteration014_augmented_family as augmented
from run_algo01_ds23_sample import read,write,sha


def configure():
    audit.binding=binding
    audit.step=binding.configure('cross_band_step')
    audit.RAW=binding.runner.RAW
    augmented.study=binding.configure('augmented')


def main():
    configure();audit.main();augmented.main()
    write(binding.runner.RAW/'recovery_independent_audit_binding.json',dict(
        all_passed=read(audit.RAW/'recovery_endpoint_audit.json')['all_passed'] and
        read(augmented.study.OUT/'independent_replay.json')['all_passed'],
        source_sha256=sha(Path(__file__)),density_and_membership_rules_unchanged=True,
        no_new_fit_or_GPS=True))


if __name__=='__main__':main()
