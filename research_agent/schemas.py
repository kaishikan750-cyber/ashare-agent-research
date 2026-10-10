from typing import Literal, Annotated
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DatasetInput(StrictModel):
    dataset_id: str = Field(default="sample_ashare", pattern=r"^[A-Za-z0-9_-]{1,80}$")


class FactorInput(DatasetInput):
    as_of: date | None = None
    limit: int = Field(default=10, ge=1, le=50)


class BacktestInput(DatasetInput):
    quantile: float = Field(default=0.2, gt=0, le=0.5)
    initial_capital: float = Field(default=1_000_000, ge=1000, le=100_000_000)
    commission_bps: float = Field(default=3, ge=0, le=100)
    stamp_duty_bps: float = Field(default=5, ge=0, le=100)
    slippage_bps: float = Field(default=5, ge=0, le=100)


StockCode = Annotated[str, Field(pattern=r"^\d{6}$")]


class Membership(StrictModel):
    code: StockCode
    known_at: date
    effective_from: date
    effective_to: date | None = None  # exclusive; must have been known at known_at

    @model_validator(mode="after")
    def chronological(self):
        if self.known_at > self.effective_from:
            raise ValueError("membership must be known by its effective date")
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must follow effective_from")
        return self


class UniverseSpec(StrictModel):
    name: str = Field(default="all", pattern=r"^[A-Za-z0-9_-]{1,40}$")
    selector: Literal["all", "sh_main", "sz_main", "custom"] = "all"
    codes: list[StockCode] = Field(default_factory=list, max_length=500)
    memberships: list[Membership] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def custom_is_explicit(self):
        if self.selector == "custom" and not (self.codes or self.memberships):
            raise ValueError("custom pool requires codes or memberships")
        if self.selector != "custom" and (self.codes or self.memberships):
            raise ValueError("codes/memberships require selector=custom")
        if self.codes and self.memberships:
            raise ValueError("use either static codes or historical memberships")
        return self


class StudySettings(StrictModel):
    train_sessions: int = Field(default=60, ge=8, le=2000)
    test_sessions: int = Field(default=20, ge=4, le=500)
    purge_sessions: int = Field(default=2, ge=2, le=20)
    quantiles: list[float] = Field(default_factory=lambda: [0.1, 0.2, 0.5], min_length=1, max_length=3)
    slippages: list[float] = Field(default_factory=lambda: [0, 5, 10], min_length=1, max_length=3)
    universes: list[UniverseSpec] = Field(default_factory=lambda: [UniverseSpec(), UniverseSpec(name="sh_main", selector="sh_main"), UniverseSpec(name="sz_main", selector="sz_main")], min_length=1, max_length=3)

    @model_validator(mode="after")
    def bounded_grid(self):
        import math
        if any(not math.isfinite(q) or not 0 < q <= 0.5 for q in self.quantiles):
            raise ValueError("quantiles must be finite in (0, 0.5]")
        if any(not math.isfinite(s) or not 0 <= s <= 100 for s in self.slippages):
            raise ValueError("slippages must be finite in [0, 100]")
        if len({u.name for u in self.universes}) != len(self.universes):
            raise ValueError("universe names must be unique")
        self.quantiles = sorted(set(self.quantiles))
        self.slippages = sorted(set(self.slippages))
        return self


class StudyInput(BacktestInput, StudySettings):
    pass


class ExperimentInput(BacktestInput):
    question: str = Field(default="评估隔夜反转因子的表现、交易成本和数据质量。", min_length=1, max_length=2000)
    mode: Literal["offline", "llm"] = "offline"
    study: StudySettings | None = None


class SensitivityInput(BacktestInput):
    quantiles: list[float] = Field(default_factory=lambda: [0.1, 0.2, 0.5], min_length=1, max_length=3)

    @model_validator(mode="after")
    def valid_quantiles(self):
        import math
        if any(not math.isfinite(q) or not 0 < q <= 0.5 for q in self.quantiles):
            raise ValueError("quantiles must be finite and in (0, 0.5]")
        return self
