"""Stage one exact fused sufficient-statistic pass in the frozen compact receiver."""

TARGET = "leo/analysis/localization_v3/discovery.py"


def revise(source):
    changes = (
        (
            "    augment_phase_statistics,\n",
            "",
            1,
        ),
        (
            "def statistics(groups, bank, corrections, height=0):",
            "def statistics(groups, bank, corrections, height=0, *, phase_derivative=None):",
            1,
        ),
        (
            "    for ci, (_, members) in enumerate(groups):\n",
            "    phase = dict(hm=[], hh=[], xh=[], zh=[])"
            " if phase_derivative is not None else None\n"
            "    for ci, (_, members) in enumerate(groups):\n",
            1,
        ),
        (
            '            z -= corrections[str(track["channel"])]\n',
            '            correction = corrections[str(track["channel"])]\n'
            "            uncorrected = (\n"
            '                z.copy(order="K")\n'
            "                if phase is not None and (correction != 0 or np.signbit(correction))\n"
            "                else None\n"
            "            )\n"
            "            z -= correction\n",
            1,
        ),
        (
            "            centered_rss.append(np.sum(centered**2, axis=1))\n",
            "            centered_rss.append(np.sum(centered**2, axis=1))\n"
            "            if phase is not None:\n"
            "                h = q * phase_derivative[:, indexes]\n"
            "                hm = h.mean(axis=1)\n"
            "                hc = h - hm[:, None]\n"
            "                phase_z = centered\n"
            "                if uncorrected is not None:\n"
            "                    phase_z = uncorrected - uncorrected.mean(axis=1)[:, None]\n"
            "                phase_time = (t - t.mean()) / 150\n"
            '                phase["hm"].append(hm)\n'
            '                phase["hh"].append(np.sum(hc * hc, axis=1))\n'
            '                phase["xh"].append(hc @ phase_time)\n'
            '                phase["zh"].append(np.sum(hc * phase_z, axis=1))\n',
            1,
        ),
        (
            '    result["count"] = np.add.reduceat(result["n"], result["starts"])\n',
            '    result["count"] = np.add.reduceat(result["n"], result["starts"])\n'
            "    if phase is not None:\n"
            "        result.update({key: np.asarray(rows) for key, rows in phase.items()})\n",
            1,
        ),
        (
            '        {str(t["channel"]): 0.0 for t in scan.tracks},\n'
            "    )\n"
            "    stats = augment_phase_statistics(stats, scan.times, base[0], base[2])\n",
            '        {str(t["channel"]): 0.0 for t in scan.tracks},\n'
            "        phase_derivative=base[2],\n"
            "    )\n",
            2,
        ),
    )
    for before, after, count in changes:
        if source.count(before) != count:
            raise ValueError("unexpected compact discovery source or call sites")
        source = source.replace(before, after)
    compile(source, TARGET, "exec")
    return source
