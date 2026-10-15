"""Read-only optional process-local MPS observation; never imports Torch."""


def sample_mps(module):
    if module is None:
        return {"status": "not_imported"}
    values, errors = {}, {}
    for field, method in (
        ("active_bytes", "current_allocated_memory"),
        ("driver_bytes", "driver_allocated_memory"),
        ("recommended_bytes", "recommended_max_memory"),
    ):
        try:
            values[field] = getattr(module.mps, method)()
        except (AttributeError, RuntimeError) as error:
            errors[field] = type(error).__name__
    if not values:
        return {"status": "unavailable", "error_type": next(iter(errors.values()))}
    if errors:
        return {"status": "partial", **values, "errors": errors}
    return {"status": "ok", **values}
