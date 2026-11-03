# Early lane response baseline

Use the original six paired-state development folds, original reception/later partition and complete four-category receiver observations. Test a local categorical predictor: add reception category counts to 20 pseudo-observations distributed according to the other-five-record training background. Freeze the resulting four probabilities before scoring later windows. No later observations enter calibration or update these probabilities. The shrinkage strength 20 is fixed before execution, not tuned.

Compare later full log density with the training-only background and saved P/U/O four-state models. Aggregate windows within recording, then weight the six recordings equally. Include every lane and empty outcome. Reproduce saved model window counts and full scores from their window exports. This is a response prediction baseline, not calibrated physical gain, target identity or location inference. Existing recordings are reused development evidence.

If the simple local model beats O on average and at least four of six recordings, future geometry models must be compared with it before claiming useful response evidence. No new geometry fit or confirmation run is triggered. One worker, at most 60 seconds, derived JSON only.
