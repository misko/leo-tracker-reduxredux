The initial sealed runner (05d74df6) read the 2.275 s training snippet,
then failed before constructing templates or fitting any model: nominees are
candidate ranks, not candidate records (`TypeError: int is not subscriptable`).
Only the training timing-abstention result was written. No held IQ was read.
The original seal and partial train directory are preserved. The corrected
runner resolves exactly those fixed ranks from the frozen receiver components;
it does not change nominations, models, splits, or outcome definitions.
The retry uses seal-v2.json and train-v2/held-v2 directories.
