from collections import defaultdict
from math import sqrt
from statistics import median
from .contracts import Track

def normalized_rate(entry, anchoring):
    return entry.rate * sqrt(anchoring/max(50,entry.pressure)) if entry.rate is not None else None

def tail_probability(reference, observed):
    if not reference:
        return None
    return (1+sum(x>=observed for x in reference))/(len(reference)+1)

def meters_by_name(records):
    pairs=defaultdict(list)
    for row in records:
        pairs[row.meter].append(row)
    return {key:sorted(rows,key=lambda row:row.start) for key,rows in sorted(pairs.items())}

def cohort_identity(group):
    if isinstance(group,dict):
        return group.get("cohort")
    return getattr(group,"cohort",None)

def cohort_distance(group):
    if isinstance(group,dict):
        return group.get("distance")
    return getattr(group,"distance",None)

def valid_rates(entries, anchoring):
    """Return pressure-normalized rates from comparable, covered windows."""
    values=[]
    for entry in entries or ():
        # 冲洗、生产夜班、覆盖不足（缺测）等窗口一律不能作为借样证据。
        if getattr(entry,"excluded",None):
            continue
        value=normalized_rate(entry,anchoring)
        if value is not None:
            values.append(value)
    return values

def _typical_level(group):
    if isinstance(group,dict):
        value=group.get("typical_lpm",0.0)
    else:
        value=getattr(group,"typical_lpm",0.0)
    return float(value) if value is not None else 0.0

def _policy_option(policy, names, default=None):
    for name in names:
        if hasattr(policy,name):
            value=getattr(policy,name)
            if value is not None:
                return value
    return default

def _baseline_with_donors(meter, group, prior, cohorts, policy, *, borrow=True):
    anchor=policy.pressure_anchor
    own=valid_rates(prior.get(meter,()),anchor)
    cohort=cohort_identity(group)
    donor_values={}
    if borrow and len(own)<policy.minimum_samples and hasattr(cohorts,"get"):
        for donor, entries in sorted(prior.items()):
            if donor==meter:
                continue
            donor_group=cohorts.get(donor)
            if cohort_identity(donor_group)!=cohort:
                continue
            # A profile already outside the accepted cohort radius is exactly
            # the distribution-shift case; do not import its raw history.
            donor_distance=cohort_distance(donor_group)
            if donor_distance is not None and donor_distance>policy.cohort_reject:
                continue
            values=valid_rates(entries,anchor)
            if values:
                donor_values[donor]=values

    if own:
        level=median(own)
    elif isinstance(group,dict) and "typical_lpm" in group:
        level=_typical_level(group)
    elif donor_values:
        level=median([median(values) for values in donor_values.values()])
    else:
        level=_typical_level(group)

    donor_samples={}
    for donor, values in donor_values.items():
        donor_level=median(values)
        donor_samples[donor]=tuple(value-donor_level+level for value in values)

    baseline=list(own)
    for donor in sorted(donor_samples):
        baseline.extend(donor_samples[donor])
    return baseline, tuple(sorted(donor_samples)), donor_samples, level

def borrowed_baseline(history, meter, cohorts, policy):
    """Public helper returning ``(baseline_values, donor_meters, samples)``."""
    prior=meters_by_name(history)
    group=cohorts[meter]
    baseline, donors, samples, _level=_baseline_with_donors(meter,group,prior,cohorts,policy)
    return tuple(baseline), donors, samples

def _assess_meter(meter,daily,prior,cohorts,policy,*,borrow=True,verify_donors=True):
    if meter not in cohorts:
        return Track(meter,daily[0].sector,"资料缺失",len(daily),0,0,None,0,"未登记","用水画像未建档",None)

    group=cohorts[meter]
    own_count=len(valid_rates(prior.get(meter,()),policy.pressure_anchor))
    baseline,donors,donor_samples,_target_level=_baseline_with_donors(
        meter,group,prior,cohorts,policy,borrow=borrow
    )
    borrowed_count=sum(len(values) for values in donor_samples.values())
    required_donors=int(_policy_option(
        policy,
        ("minimum_donors","min_donors","donor_minimum","minimum_donor_meters"),
        0,
    ) or 0)
    required_borrowed=int(_policy_option(
        policy,
        ("minimum_borrowed_samples","borrow_minimum_samples","min_borrowed_samples"),
        0,
    ) or 0)
    donor_evidence_short=(
        own_count<policy.minimum_samples
        and (len(donors)<required_donors or borrowed_count<required_borrowed)
    )

    values=[(normalized_rate(entry,policy.pressure_anchor),entry)
            for entry in daily if not entry.excluded]
    good=[(value,row) for value,row in values if value is not None]
    floor=median(baseline) if baseline else _typical_level(group)
    maximum=max((value for value,_ in good),default=floor)
    excess=max(0, maximum-floor)

    persistence=0
    longest=0
    prior_start=None
    signal={r.start:v for v,r in good}
    for entry in daily:
        value=signal.get(entry.start)
        if value is None or value-floor<policy.minimum_rate:
            persistence=0
        else:
            persistence=1 if prior_start is None or entry.start-prior_start>1500 else persistence+1
        longest=max(longest,persistence)
        prior_start=entry.start

    pvalue=tail_probability(baseline,maximum) if good else None
    isolated=max((row.test_rate for _,row in good if row.test_rate is not None),default=None)

    target_distance=cohort_distance(group)
    if target_distance is None:
        target_distance=0
    if not good:
        state,reason="需补采","目标窗口全部不可用于判断"
    elif isolated is not None and isolated>=policy.isolation_alarm:
        state,reason="关阀仍过水","隔离试验余流超过阈值"
    elif (len(baseline)<policy.minimum_samples or donor_evidence_short
          or target_distance>policy.cohort_reject):
        state,reason="人工复核","基线过少或偏离画像簇"
    elif longest>=policy.minimum_persistence and pvalue <= policy.calibration_cap:
        state,reason="疑似持续漏损","连续夜窗净余流及经验尾概率同时触发"
    else:
        state,reason="观察","未同时满足持续夜数及余流标准"

    donor_sensitive=False
    # Leave-one-donor-meter-out: if the absence of any one supplier changes the
    # original grade, borrowed evidence is not robust enough for auto grading.
    # Closure evidence belongs to the meter itself and keeps its alarm grade.
    if verify_donors and donors and state in {"疑似持续漏损","观察"}:
        for critical_donor in donors:
            reduced_prior={name:rows for name,rows in prior.items() if name!=critical_donor}
            alternate=_assess_meter(
                meter,daily,reduced_prior,cohorts,policy,
                borrow=borrow,verify_donors=False,
            )
            if alternate.status!=state:
                donor_sensitive=True
                break
        if donor_sensitive:
            state,reason="人工复核","借样分级依赖任一供样表，缺表复算会改判"

    return Track(
        meter,daily[0].sector,state,len(daily),len(good),round(excess,4),
        round(pvalue,5) if pvalue is not None else None,longest,cohort_identity(group),reason,
        round(isolated,4) if isolated is not None else None,
        borrowed_count,donors,donor_sensitive,
    )

def _visible_at_cutoff(record, as_of):
    if as_of is None:
        return True
    received=getattr(record,"received",None)
    if received is not None:
        return received<=as_of
    known_at=getattr(record,"known_at",None)
    if known_at is not None:
        return known_at<as_of
    return True

class _PolicyView:
    """Expose optional call-level policy overrides without mutating policy."""
    __slots__=("base","overrides")
    def __init__(self,base,overrides):
        object.__setattr__(self,"base",base)
        object.__setattr__(self,"overrides",overrides)
    def __getattr__(self,name):
        overrides=object.__getattribute__(self,"overrides")
        if name in overrides:
            return overrides[name]
        return getattr(object.__getattribute__(self,"base"),name)

def screen(history, recent, cohorts, policy, as_of=None, *, borrow=True, **options):
    """Grade recent meters; optional arrival stamps are filtered at ``as_of``."""
    if as_of is None:
        as_of=options.pop("at",options.pop("cutoff",None))
    history=tuple(row for row in history if _visible_at_cutoff(row,as_of))
    recent=tuple(row for row in recent if _visible_at_cutoff(row,as_of))
    overrides={}
    for name in ("minimum_donors","min_donors","donor_minimum","minimum_donor_meters",
                 "minimum_borrowed_samples","borrow_minimum_samples","min_borrowed_samples"):
        if name in options:
            overrides[name]=options.pop(name)
    active_policy=_PolicyView(policy,overrides) if overrides else policy
    verify_donors=bool(options.pop("verify_donors",True))
    prior=meters_by_name(history)
    diagnostics=[]
    for meter, daily in meters_by_name(recent).items():
        diagnostics.append(_assess_meter(
            meter,daily,prior,cohorts,active_policy,borrow=borrow,
            verify_donors=verify_donors,
        ))
    return tuple(diagnostics)
