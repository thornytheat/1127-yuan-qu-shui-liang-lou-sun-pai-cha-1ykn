from .contracts import ProfilePoint
from .medoids import fit,choose_group,best_overlap

def _asof_profiles(registry, at):
    """Select the latest profile revision visible at the shift cutoff.

    Late profiles (including a revision whose arrival time is exactly the
    cutoff, matching :func:`fit`) must not rewrite an already-run shift.
    """
    known={}
    for row in registry:
        point=ProfilePoint.parse(row)
        if point.known_at >= at:
            continue
        previous=known.get(point.key)
        if previous is None or point.known_at > previous.known_at:
            known[point.key]=point
        elif point.known_at == previous.known_at and point != previous:
            # Same-arrival conflicting profiles are nondeterministic input;
            # choose a stable content winner rather than dictionary order.
            signature=tuple(sorted(point.as_record().items()))
            old_signature=tuple(sorted(previous.as_record().items()))
            if signature < old_signature:
                known[point.key]=point
    return tuple(known[key] for key in sorted(known))

def segment_profiles(history, registry, at):
    segmentation=fit(history,at)
    indexed={}
    for point in _asof_profiles(registry,at):
        cohort,distance=choose_group(segmentation,point)
        indexed[point.key]={"meter":point.key,"sector":point.sector,"cohort":cohort,"distance":distance,
                            "typical_lpm":next(x.overnight_lpm for x in segmentation.medoids if x.key==cohort)}
    return segmentation, indexed
