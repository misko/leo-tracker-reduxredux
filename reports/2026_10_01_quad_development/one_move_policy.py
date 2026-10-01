"""Select one positive saved proposal, without geography or repeated moves."""
def choose(moves):
    best=None
    for row in moves:
        if row['mixture_gain']>1e-6 and (best is None or row['mixture_gain']>best['mixture_gain']):best=row
    return best
