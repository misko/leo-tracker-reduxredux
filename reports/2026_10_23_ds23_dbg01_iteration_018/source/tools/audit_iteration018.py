"""Audit saved018 outputs without rerunning optimization."""
import audit_ds23_iteration016_recovery as audit
import probe_ds23_iteration018_recovery as binding

if __name__=='__main__':
    audit.binding=binding
    audit.main()
