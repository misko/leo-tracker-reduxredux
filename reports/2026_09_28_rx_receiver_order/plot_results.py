"""Render the independently audited hypothesis-level opportunity counts."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
audit = json.loads((HERE / 'audit.json').read_text())
roles = ['reception', 'held_frequency']
series = [
    ('no_matching_candidate', 'No compatible candidate', '#9ca3af'),
    ('ambiguous_hypothesis', 'Multiple hypotheses', '#e69f00'),
    ('ambiguous_candidate', 'Multiple candidates', '#cc79a7'),
    ('unique_hit', 'Unique hit', '#0072b2'),
]
fig, ax = plt.subplots(figsize=(10, 4.5), layout='constrained')
bottom = [0, 0]
for key, label, color in series:
    counts = [audit['status_counts_by_role'][role].get(key, 0) for role in roles]
    ax.barh(range(2), counts, left=bottom, label=label, color=color)
    bottom = [left + value for left, value in zip(bottom, counts)]
ax.set_yticks(range(2), ['Reception period', 'Final frequency-target period'])
ax.invert_yaxis()
ax.set_xlabel('Receiver × hypothesis × window rows (not independent satellite events)')
ax.set_title('Exact-lane opportunities: unique hits are sparse', loc='left', pad=18)
ax.spines[['top', 'right']].set_visible(False)
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False)
for index, role in enumerate(roles):
    count = audit['status_counts_by_role'][role]['unique_hit']
    ax.text(bottom[index] + 150, index, f'{count} unique', va='center', fontsize=10)
ax.set_xlim(0, max(bottom) * 1.13)
fig.savefig(HERE / 'opportunity-statuses.png', dpi=180)
fig.savefig(HERE / 'opportunity-statuses.svg')
