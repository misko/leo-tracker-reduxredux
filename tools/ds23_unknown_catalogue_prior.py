"""Catalogue-aware category prior, conditional on the frozen family partition.

Each fixed family slot is unknown with mass p, or one of N named identities
with mass (1-p)/N each. Fixed aliases, partitions and continuous RF likelihoods
are unchanged. This is not marginalization over all identity/partition choices.
"""

import math


def category_code(catalogue_count, unknown_count, unknown_probability=.05):
    if (not isinstance(catalogue_count,int) or catalogue_count<1 or
            not isinstance(unknown_count,int) or unknown_count<0 or
            not 0<unknown_probability<1):
        raise ValueError('positive catalogue size, nonnegative count and interior probability required')
    return 2*unknown_count*math.log((1-unknown_probability)/(unknown_probability*catalogue_count))


def corrected_cost(old_cost,catalogue_count,unknown_count):
    """Original code was conditional on one fixed name, equivalent to N=1."""
    return old_cost+category_code(catalogue_count,unknown_count)-category_code(1,unknown_count)
