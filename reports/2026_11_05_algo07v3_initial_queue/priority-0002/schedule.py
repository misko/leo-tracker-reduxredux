def fitted_first(operation, tasks):
    """Start fitted-c arms first, then restore the original branch/arm order."""
    tasks = tuple(tasks)
    priority = sorted(range(len(tasks)), key=lambda i: (tasks[i][1] != 'fitted_c', i))
    slots = {task: i for i, task in enumerate(tasks)}
    values = map_annotation_training(lambda slot: operation(tasks[priority[slots[slot]]]), tasks)
    ordered = [None] * len(tasks)
    for index, value in zip(priority, values, strict=True):
        ordered[index] = value
    return ordered
