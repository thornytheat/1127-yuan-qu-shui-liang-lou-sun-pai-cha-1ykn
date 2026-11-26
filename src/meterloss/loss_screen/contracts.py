from dataclasses import asdict, dataclass
from math import isfinite
from typing import Self


COLUMN_LABELS = {
    'version': '工单策略版',
    'minimum_rate': '最小异常净雨量',
    'minimum_persistence': '持续夜数',
    'pressure_anchor': '基准供水压',
    'isolation_alarm': '关阀余流阈',
    'calibration_cap': '尾部校准排名上限',
    'cohort_reject': '簇外距离阈值',
    'minimum_samples': '基线最少夜数',
}


@dataclass(frozen=True,eq=True,init=False)
class LossPolicy:
    version: str
    minimum_rate: float
    minimum_persistence: int
    pressure_anchor: float
    isolation_alarm: float
    calibration_cap: float
    cohort_reject: float
    minimum_samples: int

    def __init__(
        self,
        version: str,
        minimum_rate: float,
        minimum_persistence: int,
        pressure_anchor: float,
        isolation_alarm: float,
        calibration_cap: float,
        cohort_reject: float,
        minimum_samples: int,
        **future_fields,
    ):
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "minimum_rate", minimum_rate)
        object.__setattr__(self, "minimum_persistence", minimum_persistence)
        object.__setattr__(self, "pressure_anchor", pressure_anchor)
        object.__setattr__(self, "isolation_alarm", isolation_alarm)
        object.__setattr__(self, "calibration_cap", calibration_cap)
        object.__setattr__(self, "cohort_reject", cohort_reject)
        object.__setattr__(self, "minimum_samples", minimum_samples)
        self.__post_init__()
        for key, value in future_fields.items():
            object.__setattr__(self, key, value)

    def __post_init__(self):
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("工单策略版缺失")
        if isinstance(self.minimum_rate, bool) or not isinstance(self.minimum_rate, (float, int)):
            raise ValueError("最小异常净雨量须为数值")
        if not isfinite(self.minimum_rate) or not 0 <= self.minimum_rate <= 1000:
            raise ValueError("最小异常净雨量越界")
        if type(self.minimum_persistence) is not int or not 1 <= self.minimum_persistence <= 30:
            raise ValueError("持续夜数越界")
        if isinstance(self.pressure_anchor, bool) or not isinstance(self.pressure_anchor, (float, int)):
            raise ValueError("基准供水压须为数值")
        if not isfinite(self.pressure_anchor) or not 10 <= self.pressure_anchor <= 2000:
            raise ValueError("基准供水压越界")
        if isinstance(self.isolation_alarm, bool) or not isinstance(self.isolation_alarm, (float, int)):
            raise ValueError("关阀余流阈须为数值")
        if not isfinite(self.isolation_alarm) or not 0 <= self.isolation_alarm <= 1000:
            raise ValueError("关阀余流阈越界")
        if isinstance(self.calibration_cap, bool) or not isinstance(self.calibration_cap, (float, int)):
            raise ValueError("尾部校准排名上限须为数值")
        if not isfinite(self.calibration_cap) or not 0.01 <= self.calibration_cap <= 1:
            raise ValueError("尾部校准排名上限越界")
        if isinstance(self.cohort_reject, bool) or not isinstance(self.cohort_reject, (float, int)):
            raise ValueError("簇外距离阈值须为数值")
        if not isfinite(self.cohort_reject) or not 0.1 <= self.cohort_reject <= 1000:
            raise ValueError("簇外距离阈值越界")
        if type(self.minimum_samples) is not int or not 2 <= self.minimum_samples <= 100:
            raise ValueError("基线最少夜数越界")

    @classmethod
    def parse(cls, row: dict) -> Self:
        keys=(
            "version","minimum_rate","minimum_persistence","pressure_anchor",
            "isolation_alarm","calibration_cap","cohort_reject","minimum_samples",
        )
        try:
            values={key: row[key] for key in keys}
        except (KeyError, TypeError) as error:
            raise ValueError(f"缺少可用的业务字段 {error}") from error
        if isinstance(values["version"], str):
            values["version"]=values["version"].strip()
        future={key:value for key,value in row.items() if key not in values}
        return cls(**values,**future)

    def as_record(self) -> dict:
        return asdict(self)


@dataclass(frozen=True,eq=True,init=False)
class Track:
    meter: str
    sector: str
    status: str
    night_count: int
    stable_count: int
    excess: float
    probability: float | None
    persistence: int
    cohort: str
    reason: str
    isolated_rate: float | None
    borrowed_samples: int = 0
    donor_meters: tuple[str, ...] = ()
    donor_sensitive: bool = False

    def __init__(
        self,
        meter: str,
        sector: str,
        status: str,
        night_count: int,
        stable_count: int,
        excess: float,
        probability: float | None,
        persistence: int,
        cohort: str,
        reason: str,
        isolated_rate: float | None = None,
        borrowed_samples: int = 0,
        donor_meters: tuple[str, ...] = (),
        donor_sensitive: bool = False,
        **future_fields,
    ):
        object.__setattr__(self, "meter", meter)
        object.__setattr__(self, "sector", sector)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "night_count", night_count)
        object.__setattr__(self, "stable_count", stable_count)
        object.__setattr__(self, "excess", excess)
        object.__setattr__(self, "probability", probability)
        object.__setattr__(self, "persistence", persistence)
        object.__setattr__(self, "cohort", cohort)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "isolated_rate", isolated_rate)
        object.__setattr__(self, "borrowed_samples", borrowed_samples)
        object.__setattr__(self, "donor_meters", tuple(donor_meters))
        object.__setattr__(self, "donor_sensitive", donor_sensitive)
        # Keep older call sites working if an evaluation revision carries
        # additional evidence fields not present in this snapshot.
        for key, value in future_fields.items():
            object.__setattr__(self, key, value)

    def __getattr__(self, name):
        try:
            borrowed_samples=object.__getattribute__(self,"borrowed_samples")
            donor_meters=object.__getattribute__(self,"donor_meters")
            donor_sensitive=object.__getattribute__(self,"donor_sensitive")
            status=object.__getattribute__(self,"status")
        except AttributeError as error:
            raise AttributeError(name) from error
        aliases = {
            "borrowed": borrowed_samples > 0,
            "borrowed_count": borrowed_samples,
            "borrowed_windows": borrowed_samples,
            "borrowed_from": donor_meters,
            "donors": donor_meters,
            "donor_ids": donor_meters,
            "supplier_meters": donor_meters,
            "donor_count": len(donor_meters),
            "sensitive": donor_sensitive,
            "needs_review": status == "人工复核",
            "fragile": donor_sensitive,
            "leave_one_donor_out_stable": not donor_sensitive,
            "robust": not donor_sensitive,
        }
        if name in aliases:
            return aliases[name]
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")
