/* Private qualification overlay. The original ABI structs remain unchanged. */
#ifndef LEO_PAIRED_EPOCH_UNION_H
#define LEO_PAIRED_EPOCH_UNION_H

enum { PAIRED_EPOCH_MAX_ACTIVE = 2 * 4 * 3 };

typedef struct {
    int32_t own_counts[2];
    int32_t own_centers[2][4];
    int32_t active_counts[2];
    int32_t active[2][PAIRED_EPOCH_MAX_ACTIVE];
    int32_t union_enabled;
} paired_epoch_trace;

static void paired_epoch_mark(unsigned char *selected, int frame,
    const int centers[4], int count)
{
    for (int c=0;c<count&&c<4;++c) {
        int first=centers[c]-1, last=centers[c]+1;
        if(first<0)first=0;
        if(last>=frame)last=frame-1;
        for(int epoch=first;epoch<=last;++epoch)selected[epoch]=1;
    }
}

#endif
