"""RF-only qualification. Geographic coordinates and errors are never used."""
ARMS=('c0','fitted_c')

def qualify(trial, audit, incumbent, universe):
    reasons=[]
    if not trial.get('paired_valid'):reasons.append('paired RF gates fail')
    if audit is None or not audit.get('all_verified'):reasons.append('exact replay fails or missing')
    if set(trial.get('arms',{}))!=set(ARMS):
        return dict(qualified=False,reasons=reasons+['missing matched c arm'])
    additions={}
    for arm in ARMS:
        row=trial['arms'][arm];owners=row.get('proposed_owners',{})
        ids=set(row.get('proposed_associated_ids',[]))
        if set(owners)!=ids:reasons.append(arm+': owner and point sets differ')
        if not ids<=universe:reasons.append(arm+': unknown observations')
        if any(owners.get(i)!=n for i,n in incumbent[arm].items()):
            reasons.append(arm+': published ALGO04 owners not preserved')
        if row.get('final_phase_change_s',float('inf'))>.01:
            reasons.append(arm+': phase not converged')
        additions[arm]={i:n for i,n in owners.items() if i not in incumbent[arm]}
    if additions['c0']!=additions['fitted_c']:
        reasons.append('c-arm additions differ')
    return dict(qualified=not reasons,reasons=reasons,added_points={a:len(v) for a,v in additions.items()})
