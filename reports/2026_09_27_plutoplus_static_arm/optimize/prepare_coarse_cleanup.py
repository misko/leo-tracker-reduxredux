"""Remove repeated work in the fixed differential proposal configuration."""
import shutil
from build import HERE,build
from prepare_diff import replace
root=HERE/'work/coarseclean';root.mkdir(exist_ok=False)
shutil.copytree(HERE/'work/lazyenergy/src',root/'src')
n=root/'src/native_presence';p=n/'presence.c';s=p.read_text()
s=replace(s,'    leo_presence_profile profile;', '    int *opt_peak_indices;\n    leo_presence_profile profile;')
s=replace(s,'    free(w->weighted); free(w->base); free(w->conditioned_offsets);',
    '    free(w->opt_peak_indices);\n    free(w->weighted); free(w->base); free(w->conditioned_offsets);')
s=replace(s,'    ALLOC(grid, CFO_COUNT * n); ALLOC(accumulated, CFO_COUNT * n); ALLOC(support, n);',
    '''    ALLOC(opt_peak_indices,n);
    ALLOC(grid, CFO_COUNT * n); ALLOC(accumulated, CFO_COUNT * n); ALLOC(support, n);
#if LEO_PRESENCE_DIFFERENTIAL_PROPOSAL
    for(size_t k=0;k<CFO_COUNT*n;++k) w->grid[k]=-INFINITY;
#endif''')
s=replace(s,'        for (int f = 0; f < 11; ++f) for (int e = 0; e < (int)w->n; ++e) {',
    '''        /* Differential proposals populate only row five. Other rows stay
         * -INFINITY for this workspace's entire lifetime. */
        for (int f = LEO_PRESENCE_DIFFERENTIAL_PROPOSAL ? 5 : 0;
             f < (LEO_PRESENCE_DIFFERENTIAL_PROPOSAL ? 6 : 11); ++f)
        for (int e = 0; e < (int)w->n; ++e) {''')
s=replace(s,'        for (int delta=-1; delta<=1; ++delta) {\n            int local=',
    '        for (int delta=-1; delta<=1; ++delta) {\n            if (!delta) continue; /* Retained center already has the identical native score. */\n            int local=')
p.write_text(s)
p=n/'coarse_differential.h';s=p.read_text()
s=replace(s,'    for (size_t k=0; k<CFO_COUNT*w->n; ++k) w->grid[k]=-INFINITY;','    /* Other CFO rows were initialized once and are never written here. */')
s=replace(s,'''    int epochs[8], selected=0;
    for (int selection=0; selection<8; ++selection) {
        int best=-1;
        for (int k=0; k<(int)w->n; ++k) {
            int left=k ? k-1 : (int)w->n-1, right=k+1==(int)w->n ? 0 : k+1;
            if (!(scores[k]>=scores[left] && scores[k]>=scores[right] &&
                (scores[k]>scores[left] || scores[k]>scores[right]))) continue;''',
    '''    int epochs[8], selected=0, peaks=0;
    /* Scores do not change during selection. Preserve ascending-index ties. */
    for (int k=0;k<(int)w->n;++k) {
        int left=k ? k-1 : (int)w->n-1, right=k+1==(int)w->n ? 0 : k+1;
        if(scores[k]>0 && scores[k]>=scores[left] && scores[k]>=scores[right] &&
           (scores[k]>scores[left] || scores[k]>scores[right])) w->opt_peak_indices[peaks++]=k;
    }
    for (int selection=0; selection<8; ++selection) {
        int best=-1;
        for (int index=0; index<peaks; ++index) {
            int k=w->opt_peak_indices[index];''')
p.write_text(s);build('coarseclean',root);build('coarseclean',root,host=True,sanitize=True)
