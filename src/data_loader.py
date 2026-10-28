"""Validated factory inputs and expansion of orders into routing operations."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping
import math
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ORIGIN = datetime(2026, 11, 2)  # local factory clock, Monday, no time-zone conversion
DEFAULT_HORIZON = 14 * 1440
COLUMNS = {
    "orders": ["order_id", "product_id", "quantity", "release_minute", "due_minute", "priority"],
    "machines": ["machine_id", "machine_name", "resource_group", "shift_start_minute", "shift_end_minute", "working_days"],
    "products": ["product_id", "product_name", "unit_cost", "shortage_penalty", "material_per_unit"],
    "routings": ["product_id", "operation_sequence", "operation_name", "machine_id", "minutes_per_unit", "setup_minutes"],
    "downtimes": ["machine_id", "start_minute", "end_minute", "reason"],
}

class InputError(ValueError):
    """An input does not conform to the documented factory schema."""

@dataclass
class FactoryData:
    orders: pd.DataFrame
    machines: pd.DataFrame
    products: pd.DataFrame
    routings: pd.DataFrame
    downtimes: pd.DataFrame
    origin: datetime = DEFAULT_ORIGIN
    horizon: int = DEFAULT_HORIZON

    def replace(self, **changes) -> "FactoryData":
        fields = {k: getattr(self, k) for k in COLUMNS}
        fields.update(origin=self.origin, horizon=self.horizon)
        fields.update(changes)
        return make_factory(**fields)

@dataclass(frozen=True)
class Alternative:
    machine_id: str
    minutes_per_unit: int
    setup_minutes: int
    def duration(self, quantity: int) -> int:
        return self.setup_minutes + self.minutes_per_unit * quantity

@dataclass(frozen=True)
class Operation:
    operation_id: str
    order_id: str
    product_id: str
    sequence: int
    name: str
    quantity: int
    release: int
    due: int
    priority: int
    predecessor_id: str | None
    alternatives: tuple[Alternative, ...]
    order_index: int


def operation_id(order_id: str, sequence: int) -> str:
    return f"{order_id}::{sequence:02d}"


def _strings(df: pd.DataFrame, cols: list[str], table: str) -> None:
    for c in cols:
        if df[c].isna().any():
            raise InputError(f"{table}.{c} contains blank values")
        df[c] = df[c].astype(str).str.strip()
        if (df[c] == "").any():
            raise InputError(f"{table}.{c} contains blank values")


def _integers(df: pd.DataFrame, cols: list[str], table: str) -> None:
    for c in cols:
        try:
            nums = pd.to_numeric(df[c], errors="raise")
        except (ValueError, TypeError) as exc:
            raise InputError(f"{table}.{c} must contain integers") from exc
        if nums.isna().any() or not all(math.isfinite(float(x)) and float(x).is_integer() for x in nums):
            raise InputError(f"{table}.{c} must contain finite integers")
        # Bound inputs to avoid integer overflow / accidental astronomical CP models.
        if any(abs(float(x)) > 10_000_000 for x in nums):
            raise InputError(f"{table}.{c} is outside the supported range")
        df[c] = nums.astype("int64")


def _nonnegative_numbers(df: pd.DataFrame, cols: list[str], table: str) -> None:
    for c in cols:
        try:
            nums = pd.to_numeric(df[c], errors="raise")
        except (ValueError, TypeError) as exc:
            raise InputError(f"{table}.{c} must be numeric") from exc
        if nums.isna().any() or not all(math.isfinite(float(x)) and 0 <= float(x) <= 10_000_000 for x in nums):
            raise InputError(f"{table}.{c} must be finite, nonnegative and no greater than 10,000,000")
        df[c] = nums.astype(float)


def make_factory(*, orders: pd.DataFrame, machines: pd.DataFrame, products: pd.DataFrame,
                 routings: pd.DataFrame, downtimes: pd.DataFrame | None = None,
                 origin: datetime = DEFAULT_ORIGIN, horizon: int = DEFAULT_HORIZON) -> FactoryData:
    frames = dict(orders=orders, machines=machines, products=products, routings=routings,
                  downtimes=downtimes if downtimes is not None else pd.DataFrame(columns=COLUMNS["downtimes"]))
    if not isinstance(origin, datetime) or origin.tzinfo is not None or origin.hour or origin.minute or origin.second or origin.microsecond:
        raise InputError("Factory origin must be a timezone-naive local date at 00:00")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 90 * 1440:
        raise InputError("Horizon must be an integer number of minutes in 1..129600 (90 days)")
    for name, frame in frames.items():
        if not isinstance(frame, pd.DataFrame):
            raise InputError(f"{name} must be a CSV table")
        missing = set(COLUMNS[name]) - set(frame.columns)
        if missing:
            raise InputError(f"{name} is missing columns: {', '.join(sorted(missing))}")
        frames[name] = frame.loc[:, COLUMNS[name]].copy().reset_index(drop=True)
    o, m, p, r, d = (frames[x] for x in ("orders", "machines", "products", "routings", "downtimes"))
    if m.empty or p.empty or r.empty:
        raise InputError("Machines, products and routings must not be empty")
    _strings(o, ["order_id", "product_id"], "orders")
    _integers(o, ["quantity", "release_minute", "due_minute", "priority"], "orders")
    _strings(m, ["machine_id", "machine_name", "resource_group", "working_days"], "machines")
    _integers(m, ["shift_start_minute", "shift_end_minute"], "machines")
    _strings(p, ["product_id", "product_name"], "products")
    _nonnegative_numbers(p, ["unit_cost", "shortage_penalty"], "products")
    _integers(p, ["material_per_unit"], "products")
    _strings(r, ["product_id", "operation_name", "machine_id"], "routings")
    _integers(r, ["operation_sequence", "minutes_per_unit", "setup_minutes"], "routings")
    _strings(d, ["machine_id", "reason"], "downtimes")
    _integers(d, ["start_minute", "end_minute"], "downtimes")
    for df, col, name in [(o, "order_id", "orders"), (m, "machine_id", "machines"), (p, "product_id", "products")]:
        if df[col].duplicated().any():
            raise InputError(f"{name}.{col} must be unique")
    if o.order_id.str.contains("::", regex=False).any():
        raise InputError("Order IDs cannot contain the reserved sequence delimiter '::'")
    if ((o.quantity <= 0) | (o.release_minute < 0) | (o.due_minute < o.release_minute) | ~o.priority.between(1, 5)).any():
        raise InputError("Orders require quantity > 0, 0 <= release <= due and priority 1..5")
    if ((m.shift_start_minute < 0) | (m.shift_end_minute > 1440) | (m.shift_start_minute >= m.shift_end_minute)).any():
        raise InputError("Shifts must be same-day intervals with 0 <= start < end <= 1440")
    for v in m.working_days:
        parts = v.split("|")
        if not parts or any(x not in set("0123456") for x in parts) or len(set(parts)) != len(parts):
            raise InputError("working_days must be pipe-separated weekday digits 0..6, Monday=0")
    if (p.material_per_unit < 0).any():
        raise InputError("material_per_unit must be nonnegative")
    if ((r.operation_sequence < 1) | (r.minutes_per_unit <= 0) | (r.setup_minutes < 0)).any():
        raise InputError("Routing requires sequence >= 1, processing > 0 and setup >= 0")
    if r.duplicated(["product_id", "operation_sequence", "machine_id"]).any():
        raise InputError("Duplicate eligible machine for one product operation")
    if ((d.start_minute < 0) | (d.end_minute <= d.start_minute)).any():
        raise InputError("Downtime requires 0 <= start < end")
    if not set(o.product_id).issubset(set(p.product_id)):
        raise InputError("Every ordered product must exist in products.csv")
    if not set(r.product_id).issubset(set(p.product_id)) or set(p.product_id) != set(r.product_id):
        raise InputError("Every product must have a routing and all routings must reference a product")
    if not set(r.machine_id).issubset(set(m.machine_id)) or not set(d.machine_id).issubset(set(m.machine_id)):
        raise InputError("All routing and downtime machines must exist in machines.csv")
    groups = m.set_index("machine_id").resource_group.to_dict()
    for product, rr in r.groupby("product_id", sort=False):
        sequences = sorted(rr.operation_sequence.unique().tolist())
        if sequences != list(range(1, len(sequences) + 1)):
            raise InputError(f"{product}: operation sequences must be consecutive starting at 1")
        for seq, op in rr.groupby("operation_sequence"):
            if op.operation_name.nunique() != 1:
                raise InputError(f"{product} sequence {seq}: alternatives need the same operation name")
            if len({groups[x] for x in op.machine_id}) != 1:
                raise InputError(f"{product} sequence {seq}: alternatives must belong to the same resource group")
    return FactoryData(**frames, origin=origin, horizon=horizon)


def load_sample() -> FactoryData:
    frames = {k: pd.read_csv(ROOT / "data" / f"{k}.csv", dtype={"working_days": str} if k == "machines" else None) for k in COLUMNS}
    return make_factory(**frames)


def build_operations(factory: FactoryData) -> list[Operation]:
    operations: list[Operation] = []
    by_product = {p: g for p, g in factory.routings.groupby("product_id", sort=False)}
    for order_index, order in enumerate(factory.orders.itertuples(index=False)):
        route = by_product[order.product_id]
        for seq, candidates in route.groupby("operation_sequence", sort=True):
            alternatives = tuple(Alternative(str(x.machine_id), int(x.minutes_per_unit), int(x.setup_minutes))
                                 for x in candidates.itertuples(index=False))
            operations.append(Operation(
                operation_id=operation_id(order.order_id, int(seq)), order_id=order.order_id,
                product_id=order.product_id, sequence=int(seq), name=str(candidates.iloc[0].operation_name),
                quantity=int(order.quantity), release=int(order.release_minute), due=int(order.due_minute),
                priority=int(order.priority), predecessor_id=operation_id(order.order_id, int(seq) - 1) if seq > 1 else None,
                alternatives=alternatives, order_index=order_index,
            ))
    return operations


def schedule_row(op: Operation, alternative: Alternative, start: int) -> dict:
    processing = alternative.minutes_per_unit * op.quantity
    return {"operation_id": op.operation_id, "order_id": op.order_id, "product_id": op.product_id,
            "operation_sequence": op.sequence, "operation_name": op.name,
            "predecessor_operation_id": op.predecessor_id or "", "quantity": op.quantity,
            "machine_id": alternative.machine_id, "start": int(start),
            "finish": int(start + alternative.setup_minutes + processing),
            "setup_minutes": alternative.setup_minutes, "processing_minutes": processing,
            "release_minute": op.release, "due_minute": op.due, "priority": op.priority,
            "segment_type": "scheduled"}
