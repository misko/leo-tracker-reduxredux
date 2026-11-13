"""ALGO07v5 composition over the owned full-budget native job."""

from copy import deepcopy
from pathlib import Path

from leo.analysis.localization_v5.initial_control import POLICY, initial_control
from leo.contracts import localization_v5
from leo.contracts.digests import canonical_digest
from leo.operations import localization_v3_job


def make_request(v3_request, backend_manifest, *, annotation_training_policy=None,
                 inclusion_control_policy=None, joint_schedule_policy=None,
                 recovery_target_limit=None, initial_seed_policy=None,
                 initial_ranking_policy=None, direct_gap_policy=None):
    from leo.analysis.localization_v4.backend import read_manifest, validate_manifest

    localization_v3_job.validate_request(v3_request)
    manifest = validate_manifest(read_manifest(backend_manifest))
    job = deepcopy(v3_request)
    binding = dict(request=v3_request, backend_manifest=manifest, initial_control_policy=POLICY)
    training = {}
    if annotation_training_policy is not None:
        training["annotation_training_policy"] = localization_v5.annotation_training_policy(
            annotation_training_policy)
        binding.update(training)
    controls = {}
    if inclusion_control_policy is not None:
        controls['inclusion_control_policy'] = localization_v5.inclusion_control_policy(
            inclusion_control_policy)
        binding.update(controls)
    joint = {}
    if joint_schedule_policy is not None:
        joint['joint_schedule_policy'] = localization_v5.joint_schedule_policy(
            joint_schedule_policy)
        binding.update(joint)
    targets = {}
    if recovery_target_limit is not None:
        targets['recovery_target_policy'] = localization_v5.recovery_target_policy(
            recovery_target_limit)
        binding.update(targets)
    discovery = {}
    if initial_seed_policy is not None or initial_ranking_policy is not None:
        discovery['initial_discovery_policy'] = localization_v5.initial_discovery_policy(
            'legacy' if initial_seed_policy is None else initial_seed_policy,
            'legacy' if initial_ranking_policy is None else initial_ranking_policy)
        binding.update(discovery)
    direct = {}
    if direct_gap_policy is not None:
        if recovery_target_limit != 0:
            raise ValueError('Direct gap policy requires explicit zero recovery targets')
        direct['direct_gap_policy'] = localization_v5.direct_gap_policy(direct_gap_policy)
        binding.update(direct)
    job["identity"]["run_id"] = "v5-" + canonical_digest(
        binding
    )[7:47]
    return validate_request(dict(
        schema_version=(7 if direct else 6 if discovery else 5 if targets else 4 if joint
                        else 3 if controls else 2 if training else 1),
        algorithm=localization_v5.MODEL,
        backend_manifest=deepcopy(manifest),
        initial_control_policy=POLICY,
        job=job,
        **training,
        **controls,
        **joint,
        **targets,
        **discovery,
        **direct,
    ))


def validate_request(request):
    from leo.analysis.localization_v4.backend import validate_manifest

    keys = {"schema_version", "algorithm", "backend_manifest", "initial_control_policy", "job"}
    if (isinstance(request, dict) and type(request.get("schema_version")) is int
            and request["schema_version"] == 2):
        keys.add("annotation_training_policy")
    if (isinstance(request, dict) and type(request.get("schema_version")) is int
            and request['schema_version'] == 3):
        keys.add('inclusion_control_policy')
        if 'annotation_training_policy' in request:
            keys.add('annotation_training_policy')
    if (isinstance(request, dict) and type(request.get('schema_version')) is int
            and request['schema_version'] == 4):
        keys.add('joint_schedule_policy')
        keys.update(k for k in ('annotation_training_policy', 'inclusion_control_policy')
                    if k in request)
    if (isinstance(request, dict) and type(request.get('schema_version')) is int
            and request['schema_version'] == 5):
        keys.add('recovery_target_policy')
        keys.update(k for k in ('annotation_training_policy', 'inclusion_control_policy',
                                'joint_schedule_policy') if k in request)
    if (isinstance(request, dict) and type(request.get('schema_version')) is int
            and request['schema_version'] == 6):
        keys.add('initial_discovery_policy')
        keys.update(k for k in ('annotation_training_policy', 'inclusion_control_policy',
                                'joint_schedule_policy', 'recovery_target_policy')
                    if k in request)
    if (isinstance(request, dict) and type(request.get('schema_version')) is int
            and request['schema_version'] == 7):
        keys.update(('direct_gap_policy', 'recovery_target_policy'))
        keys.update(k for k in ('annotation_training_policy', 'inclusion_control_policy',
                                'joint_schedule_policy', 'initial_discovery_policy')
                    if k in request)
    if (
        not isinstance(request, dict)
        or set(request) != keys
        or type(request["schema_version"]) is not int
        or request["schema_version"] not in (1, 2, 3, 4, 5, 6, 7)
        or request["algorithm"] != localization_v5.MODEL
        or request["initial_control_policy"] != POLICY
    ):
        raise ValueError("Complete native ALGO07v5 request required")
    if 'annotation_training_policy' in request:
        localization_v5.validate_annotation_training_policy(request["annotation_training_policy"])
    if 'inclusion_control_policy' in request:
        localization_v5.validate_inclusion_control_policy(request['inclusion_control_policy'])
    if 'joint_schedule_policy' in request:
        localization_v5.validate_joint_schedule_policy(request['joint_schedule_policy'])
    if 'recovery_target_policy' in request:
        localization_v5.validate_recovery_target_policy(request['recovery_target_policy'])
    if 'initial_discovery_policy' in request:
        localization_v5.validate_initial_discovery_policy(request['initial_discovery_policy'])
    if 'direct_gap_policy' in request:
        localization_v5.validate_direct_gap_policy(request['direct_gap_policy'])
        if request['recovery_target_policy']['maximum_targets'] != 0:
            raise ValueError('Direct gap policy requires explicit zero recovery targets')
    localization_v3_job.validate_request(request["job"])
    if not request["job"]["identity"]["run_id"].startswith("v5-"):
        raise ValueError("Native ALGO07v5 run namespace required")
    validate_manifest(request["backend_manifest"], check_artifacts=False)
    return request


def execute(request, *, native_manifest, receipts, resume_only=False, emit=lambda value: None):
    from leo.analysis.localization_v4.backend import ProcessBound, read_manifest
    from leo.storage.localization_v5 import LocalizationV5Store

    validate_request(request)
    training = {}
    if 'annotation_training_policy' in request:
        training["annotation_training_policy"] = request["annotation_training_policy"]
    controls = ({'inclusion_control_policy': request['inclusion_control_policy']}
                if 'inclusion_control_policy' in request else {})
    joint = ({'joint_schedule_policy': request['joint_schedule_policy']}
             if 'joint_schedule_policy' in request else {})
    targets = ({'recovery_target_policy': request['recovery_target_policy']}
               if 'recovery_target_policy' in request else {})
    discovery = ({'initial_discovery_policy': request['initial_discovery_policy']}
                 if 'initial_discovery_policy' in request else {})
    direct = ({'direct_gap_policy': request['direct_gap_policy']}
              if 'direct_gap_policy' in request else {})
    manifest = request["backend_manifest"]
    if read_manifest(native_manifest) != manifest:
        raise ValueError("Native manifest differs from request backend binding")
    # Saved publication can complete without loading the native solver or reading inputs.
    store = LocalizationV5Store(request["job"]["output_root"])
    run_id = request["job"]["identity"]["run_id"]
    try:
        store.receipt(run_id)
    except FileNotFoundError:
        if resume_only:
            raise ValueError("No committed native scientific result to resume") from None
        backend = ProcessBound(manifest, Path(receipts))
    else:
        backend = None

    def check_saved(evidence):
        provenance = evidence["provenance"]
        if (
            provenance["algorithm"] != localization_v5.MODEL
            or provenance["native_backend"]["manifest"] != manifest
            or provenance["initial_control_policy"] != POLICY
            or ("annotation_training_policy" in provenance) != bool(training)
            or provenance.get("annotation_training_policy") != training.get(
                "annotation_training_policy")
            or ('inclusion_control_policy' in provenance) != bool(controls)
            or provenance.get('inclusion_control_policy') != controls.get(
                'inclusion_control_policy')
            or (not controls and 'inclusion_control_work' in provenance)
            or ('joint_schedule_policy' in provenance) != bool(joint)
            or provenance.get('joint_schedule_policy') != joint.get('joint_schedule_policy')
            or (not joint and 'joint_schedule_work' in provenance)
            or ('recovery_target_policy' in provenance) != bool(targets)
            or provenance.get('recovery_target_policy') != targets.get('recovery_target_policy')
            or ('initial_discovery_policy' in provenance) != bool(discovery)
            or provenance.get('initial_discovery_policy') != discovery.get(
                'initial_discovery_policy')
            or ('direct_gap_policy' in provenance) != bool(direct)
            or provenance.get('direct_gap_policy') != direct.get('direct_gap_policy')
        ):
            raise ValueError("Saved result belongs to a different native backend")
        if training:
            from leo.operations.localization_v5_training import validate_provenance

            work = provenance.get("annotation_training_work")
            if work is not None:
                validate_provenance(work, request["annotation_training_policy"])
            elif (request["annotation_training_policy"]["id"]
                  == localization_v5.ANNOTATION_FALLBACK_POLICY):
                raise ValueError("Saved fallback result requires annotation training work")
        if controls:
            localization_v5.validate_inclusion_control_work(
                provenance.get('inclusion_control_work'), request['inclusion_control_policy'],
                canonical_digest(manifest))
        if joint:
            localization_v5.validate_joint_schedule_work(
                provenance.get('joint_schedule_work'), request['joint_schedule_policy'],
                canonical_digest(manifest))
        if targets:
            localization_v5.validate_target_selection(
                evidence['audit'].get('recovery_inventory'), request['recovery_target_policy'])
        if discovery:
            localization_v5.validate_initial_discovery_selection(
                evidence['audit'].get('initial'), request['initial_discovery_policy'])
        else:
            initial = evidence.get('audit', {}).get('initial')
            if isinstance(initial, dict) and 'initial_discovery_policy' in initial:
                raise ValueError('Initial discovery selection requires its explicit policy')
        gap = evidence.get('audit', {}).get('gap_recovery')
        if direct:
            localization_v5.validate_direct_gap_selection(gap, request['direct_gap_policy'])
        elif isinstance(gap, dict) and 'policy' in gap:
            raise ValueError('Direct gap selection requires its explicit policy')

    execution = {}
    if discovery and backend is not None:
        execution['initial_discovery_policy'] = request['initial_discovery_policy']
    if targets and backend is not None:
        execution['recovery_target_limit'] = request['recovery_target_policy']['maximum_targets']
    if direct and backend is not None:
        execution['direct_gap_policy'] = request['direct_gap_policy']
    work = None
    control_factory = None
    schedule_factory = None
    if joint and backend is not None:
        from leo.operations.localization_v5_joint import JointScheduleFactory

        schedule_factory = JointScheduleFactory(backend, request['joint_schedule_policy'])
        execution['joint_schedule_factory'] = schedule_factory
    if controls and backend is not None:
        from leo.operations.localization_v5_controls import ControlCacheFactory

        control_factory = ControlCacheFactory(backend, request['inclusion_control_policy'])
        execution['inclusion_control_factory'] = control_factory
    if training and backend is not None:
        if (request["annotation_training_policy"]["id"]
                == localization_v5.ANNOTATION_FALLBACK_POLICY):
            from leo.analysis.localization_v5.annotation_fallback import fit
        else:
            from leo.analysis.localization_v5.annotation_training import fit
        from leo.operations.localization_v5_training import ProcessTrainingFit

        localization_v5.validate_annotation_training_policy(fit.policy)
        if fit.policy != request["annotation_training_policy"]:
            raise ValueError("Implementation annotation training policy differs from request")
        work = ProcessTrainingFit(fit, Path(receipts))
        execution["annotation_training_fit"] = work

    return localization_v3_job._execute(
        request["job"], resume_only=resume_only, emit=emit,
        contract=localization_v5, results_factory=LocalizationV5Store,
        request_binding=request, bound=backend,
        check_saved=check_saved, initial_control=initial_control,
        extra_provenance=lambda: dict(
            algorithm=localization_v5.MODEL, native_backend=backend.provenance(),
            initial_control_policy=POLICY, **training, **controls, **joint, **targets,
            **discovery, **direct,
            **({"annotation_training_work": work.provenance()} if work is not None else {}),
            **({'inclusion_control_work': control_factory.provenance()}
               if control_factory is not None else {}),
            **({'joint_schedule_work': schedule_factory.provenance()}
               if schedule_factory is not None else {}),
        ),
        **execution,
    )
