#ifndef LEO_LANE_SCREEN_H
#define LEO_LANE_SCREEN_H

/* Optional decision record. The public result ABI is unchanged. */
typedef struct {
    double threshold;
    double coarse_max;
    int32_t rejected;
} leo_lane_screen;

#endif
