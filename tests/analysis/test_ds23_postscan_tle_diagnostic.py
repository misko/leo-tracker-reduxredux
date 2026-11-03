from export_ds23_postscan_tles import select_post_versions
import numpy as np
from plot_ds23_0268_remaining_tracks import alias_lines,wrapped_residual
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
from investigate_ds23_0268_remaining_tracks import fine_receiver_basis


def test_post_selection_uses_time_only_and_rejects_old_epoch_late_collection():
    def row(n, epoch, collection):
        return dict(norad=n,element_epoch_utc_ns=epoch,collected_utc_ns=collection)
    records=[row(1,95,130),row(1,125,160),row(1,110,170),row(1,110,150),row(2,115,140),row(3,105,120)]
    selected=select_post_versions(records,{1,2},100)
    assert selected=={1:records[3],2:records[4]}


def test_native_alias_copies_keep_exact_modulo_residuals():
    prediction=np.array([-3000.,4000.]);copies=alias_lines(prediction,-2*PERIOD,2*PERIOD)
    assert len(copies)==5
    for line in copies:
        finite=np.isfinite(line)
        np.testing.assert_allclose(wrapped_residual(line[finite],prediction[finite]),0,atol=1e-9)


def test_finer_receiver_prior_keeps_scan_average_variance_and_no_affine_mode():
    times=np.arange(301.);basis=fine_receiver_basis(times)
    np.testing.assert_allclose(np.sum(basis**2),np.sum(projected_receiver_basis(times)**2),rtol=1e-12)
    affine=np.column_stack((np.ones(len(times)),(times-150)/150))
    np.testing.assert_allclose(affine.T@basis,0,atol=1e-12)


def test_receiver_prior_normalization_does_not_depend_on_a_tracks_time_span():
    times=np.arange(301.);selection=np.array([7,42,121,150,177,240,299])
    np.testing.assert_allclose(fine_receiver_basis(times[selection]),fine_receiver_basis(times)[selection],atol=1e-14)
