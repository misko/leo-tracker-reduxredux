def _fit_lbfgsb(d, targets, arm, method, phase_step):
    families = [NewFamily(d['scan'], group, d['model'], phase_step=phase_step, allow_uncalibrated_label=True) for group in targets]
    x = np.zeros(2)
    reference = np.zeros(len(d['means']))
    history = []
    for _iteration in range(5):
        kw = {'base_problem_factory': d['problem_factory']} if 'problem_factory' in d else {}
        p = make_event_problem(d['scan'], d['node'], d['keep'], arm, reference, d['powers'], d['means'], d['model'], [], **kw)
        numerics.check_problem(d, p)
        attach_event_predictive(p, d['entries'], d['powers'])
        cached(p)

        def objective(z, p=p):
            c = p.calculate(z)
            penalty = float(np.sum(np.minimum(0, c['elevation'][p.keep]) ** 2) / 4)
            addition = 0.0 if method == 'control' else evidence(families, p, z, d, method)
            return c['negative_twice_elbo'] + penalty + addition
        opt = numerics.minimize(d, minimize, objective, x, method='L-BFGS-B', bounds=[(-12.5, 12.5)] * 2, options=dict(maxiter=48, maxfun=240, eps=0.001, ftol=1e-10, gtol=0.0001, maxls=20))
        x = np.asarray(opt.x)
        reference, check = numerics.refresh(d, p, p.state(x)['phases'][p.labels], reference)
        row = dict(endpoint_east_north_km=x, objective=float(opt.fun), success=bool(opt.success), message=str(opt.message), nfev=opt.nfev, **check)
        history.append(row)
    result = summary(p, x, d['entries'])
    result['history'] = history
    result['method'] = method
    result['arm'] = arm
    result['incumbent_objective'] = result['negative_twice_elbo']
    final_joint_result = joint_density(d, *joint_inputs(families, p, x, d['powers'], d['entries']))
    result['joint_evidence'] = final_joint_result['negative_twice_log_density']
    result['factorized_evidence'] = evidence(families, p, x, d, 'factorized')
    if method != 'control':
        result['negative_twice_elbo'] += result[method + '_evidence']
    result['joint_phase_result'] = final_joint_result
    result['joint_phase_grid_s'] = [f.phases for f in families]
    result['association_authorized'] = False
    result['pending_checks'] = ['joint target physical residuals', 'exact incumbent orbit replay', 'membership and ownership', 'local phase quadrature agreement']
    return result
