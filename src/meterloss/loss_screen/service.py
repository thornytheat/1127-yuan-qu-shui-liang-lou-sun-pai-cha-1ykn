from dataclasses import asdict
from .contracts import LossPolicy
from .scoring import screen,tail_probability

def assess(baseline,samples,usage,controls,as_of=None,**options):
    cutoff=as_of
    if cutoff is None:
        cutoff=options.get("at",options.get("cutoff"))
    policy=LossPolicy.parse(controls)
    findings=screen(baseline,samples,usage,policy,cutoff)
    return policy,findings

def evidence(findings, policy):
    out=[]
    for item in findings:
        row=asdict(item)
        row["version"]=policy.version
        row["followup"]=item.status in {"关阀仍过水","疑似持续漏损","人工复核"}
        out.append(row)
    return out
