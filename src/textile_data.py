"""Validated Zenodo adapter. Source tasks/modes are not synthetic order routings.

Times are five-minute *working* slots; no dates or costs are invented.  The
source's first/second task labels conflict with its accompanying paper, so the
order direction is an explicit parameter. Product task lists are requirements,
not inferred route sequences; same-unit task exclusivity is a selectable assumption.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
import json
import math

DATASET_URL = "https://zenodo.org/records/4106746"
INPUT_URL = "https://zenodo.org/records/4106746/files/Input_JSON_Schedule_Optimization.json?download=1"
OUTPUT_URL = "https://zenodo.org/records/4106746/files/Output_JSON_Schedule_Optimization.json?download=1"
PAPER_URL = "https://doi.org/10.3390/en14020462"
INPUT_SHA256 = "5cecb2eb95437d6b789726f302860cefb446731af9eadba2a8379af5644ed169"
BUNDLED_INPUT = Path(__file__).resolve().parents[1] / "data" / "textile" / "Input_JSON_Schedule_Optimization.json"
SLOT_MINUTES = 5

class TextileInputError(ValueError):
    """The source JSON is malformed or contains unsupported semantics."""

@dataclass(frozen=True)
class TextileMode:
    id: str
    power: tuple[float, ...]
    @property
    def duration(self) -> int:
        return len(self.power)

@dataclass(frozen=True)
class TextileChoice:
    machine_id: str
    mode_id: str
    duration: int

@dataclass(frozen=True)
class TextileOperation:
    operation_id: str
    unit_id: str
    request_index: int
    unit_index: int
    product: str
    task: str
    task_index: int
    run_index: int
    deadline: int | None
    choices: tuple[TextileChoice, ...]
    predecessors: tuple[str, ...] = ()
    symmetry_predecessor: str | None = None

@dataclass(frozen=True)
class TextileInstance:
    cell_id: str
    machines: tuple[str, ...]
    modes: dict[str, TextileMode]
    task_modes: dict[str, tuple[str, ...]]
    machine_modes: dict[str, tuple[str, ...]]
    products: dict[str, tuple[tuple[str, int], ...]]
    requests: tuple[dict, ...]
    operations: tuple[TextileOperation, ...]
    order_pairs: tuple[tuple[str, str], ...]
    collision_pairs: tuple[tuple[str, str], ...]
    horizon: int
    time_leaps: tuple[int, ...]
    grid_prices: tuple[float, ...]
    solar_availability: tuple[float, ...]
    order_interpretation: str
    unit_exclusive: bool
    input_hash: str
    warnings: tuple[str, ...]
    source_stop_seconds: int | None

    @property
    def windows(self) -> tuple[tuple[int, int], ...]:
        edges = (0, *self.time_leaps, self.horizon)
        return tuple(zip(edges, edges[1:]))

    @property
    def total_units(self) -> int:
        return sum(r["amount"] for r in self.requests)


def _shape(value: Any, path: str, expected: type) -> None:
    if not isinstance(value, expected):
        raise TextileInputError(f"{path} must be {expected.__name__}")


def _keys(value: Any, path: str, required: set[str], optional: set[str] | None = None) -> None:
    _shape(value, path, dict)
    missing = required - value.keys()
    unknown = value.keys() - required - (optional or set())
    if missing: raise TextileInputError(f"{path} missing required fields: {', '.join(sorted(missing))}")
    if unknown: raise TextileInputError(f"{path} contains unsupported fields: {', '.join(sorted(unknown))}")


def _str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TextileInputError(f"{path} must be a nonempty string")
    return value  # Preserve exact source names including accented characters and spaces.


def _int(value: Any, path: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise TextileInputError(f"{path} must be an integer in {minimum}..{maximum}")
    return value


def _num(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0:
        raise TextileInputError(f"{path} must be a finite nonnegative number")
    return float(value)


def _unique(items: list[str], path: str) -> None:
    if len(set(items)) != len(items):
        raise TextileInputError(f"{path} contains duplicate identifiers")


def _names(value: Any, path: str) -> tuple[str, ...]:
    _shape(value, path, list)
    if not value: raise TextileInputError(f"{path} must not be empty")
    result = tuple(_str(x, path) for x in value)
    _unique(list(result), path)
    return result


def _unique_json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise TextileInputError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _vector(value: Any, path: str, length: int | None = None) -> tuple[float, ...]:
    _shape(value, path, list)
    if not value or (length is not None and len(value) != length):
        raise TextileInputError(f"{path} must contain {'exactly ' + str(length) if length is not None else 'at least one'} value(s)")
    return tuple(_num(x, f"{path}[{i}]") for i, x in enumerate(value))


@lru_cache(maxsize=1)
def download_published_input() -> bytes:
    """Download once per process, verify the pinned published input; no rerun downloads."""
    try:
        request = Request(INPUT_URL, headers={"User-Agent": "SmartProductionOptimiser/1.0"})
        with urlopen(request, timeout=20) as response:
            data = response.read(2_000_001)
    except Exception as exc:
        raise TextileInputError(f"Could not download the Zenodo input: {exc}") from exc
    if len(data) > 2_000_000 or sha256(data).hexdigest() != INPUT_SHA256:
        raise TextileInputError("Downloaded input does not match the pinned Zenodo SHA-256 checksum")
    return data


def load_published_bytes() -> tuple[bytes, str]:
    """Prefer the small bundled file; fetch only if it is unavailable."""
    try:
        data = BUNDLED_INPUT.read_bytes()
        if sha256(data).hexdigest() != INPUT_SHA256:
            raise TextileInputError("Bundled textile input failed its SHA-256 check")
        return data, "Bundled local copy (SHA-256 verified)"
    except FileNotFoundError:
        return download_published_input(), "Zenodo download (cached and SHA-256 verified)"
    except OSError as exc:
        raise TextileInputError(f"Cannot read bundled input: {exc}") from exc


def parse_textile_json(blob: bytes | str, order_interpretation: str = "json", *, unit_exclusive: bool = True) -> TextileInstance:
    """Parse the supported source schema; reject unknown constraints/fields.

    order_interpretation='json': first_task before second_task, by field names.
    'paper': second before first, matching the accompanying article's prose.
    unit_exclusive=True assumes one task per product unit at a time. False allows
    independent tasks in the same unit to overlap, as observed in the workbook.
    """
    if order_interpretation not in {"json", "paper"}:
        raise TextileInputError("Order interpretation must be 'json' or 'paper'")
    if not isinstance(unit_exclusive, bool):
        raise TextileInputError("unit_exclusive must be a boolean")
    if not isinstance(blob, (bytes, str)):
        raise TextileInputError("Textile input must be JSON bytes or text")
    try:
        raw_bytes = blob.encode("utf-8") if isinstance(blob, str) else blob
        if len(raw_bytes) > 2_000_000: raise TextileInputError("Textile input exceeds 2 MB")
        raw = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_unique_json_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TextileInputError(f"Invalid UTF-8 / JSON: {exc}") from exc
    required = {"cells", "task_modes", "tasks", "machines", "products", "constraints", "energy_sources", "product_requests", "configuration"}
    _keys(raw, "root", required)
    for key in required - {"configuration"}:
        _shape(raw[key], key, list)
    _keys(raw["configuration"], "configuration", {"time_window", "time_leap", "stop_condition"})
    cfg = raw["configuration"]
    horizon = _int(cfg["time_window"], "configuration.time_window", 1, 100_000)
    _shape(cfg["time_leap"], "configuration.time_leap", list)
    leaps = tuple(_int(x, "configuration.time_leap", 1, horizon - 1) for x in cfg["time_leap"])
    if tuple(sorted(set(leaps))) != leaps:
        raise TextileInputError("configuration.time_leap must be sorted and unique")
    _keys(cfg["stop_condition"], "configuration.stop_condition", {"seconds"})
    stop_seconds = _int(cfg["stop_condition"]["seconds"], "configuration.stop_condition.seconds", 1, 1_000_000)

    modes: dict[str, TextileMode] = {}
    for i, row in enumerate(raw["task_modes"]):
        p = f"task_modes[{i}]"; _keys(row, p, {"id", "power"})
        name = _str(row["id"], f"{p}.id")
        if name in modes: raise TextileInputError(f"Duplicate task mode: {name}")
        power = _vector(row["power"], f"{p}.power")
        if len(power) > horizon: raise TextileInputError(f"{p}.power is longer than the horizon")
        modes[name] = TextileMode(name, power)
    if not modes: raise TextileInputError("task_modes must not be empty")

    task_modes: dict[str, tuple[str, ...]] = {}
    for i, row in enumerate(raw["tasks"]):
        p = f"tasks[{i}]"; _keys(row, p, {"id", "task_modes"}); name = _str(row["id"], p + ".id")
        if name in task_modes: raise TextileInputError(f"Duplicate task: {name}")
        task_modes[name] = _names(row["task_modes"], p + ".task_modes")
        if not set(task_modes[name]) <= modes.keys(): raise TextileInputError(f"{p} references an unknown mode")
    all_task_modes = [mode for items in task_modes.values() for mode in items]
    _unique(all_task_modes, "task mode ownership")
    if set(all_task_modes) != set(modes): raise TextileInputError("Every mode must belong to exactly one task")

    machine_modes: dict[str, tuple[str, ...]] = {}
    for i, row in enumerate(raw["machines"]):
        p = f"machines[{i}]"; _keys(row, p, {"id", "task_modes"}); name = _str(row["id"], p + ".id")
        if name in machine_modes: raise TextileInputError(f"Duplicate machine: {name}")
        machine_modes[name] = _names(row["task_modes"], p + ".task_modes")
        if not set(machine_modes[name]) <= modes.keys(): raise TextileInputError(f"{p} references an unknown mode")
    if len(raw["cells"]) != 1: raise TextileInputError("Only a single production cell is currently supported")
    cell = raw["cells"][0]; _keys(cell, "cells[0]", {"id", "machines"})
    cell_id, machines = _str(cell["id"], "cells[0].id"), _names(cell["machines"], "cells[0].machines")
    if set(machines) != set(machine_modes): raise TextileInputError("Cell machines must match the machine records exactly")
    choices_by_task: dict[str, tuple[TextileChoice, ...]] = {}
    for task, mids in task_modes.items():
        choices_by_task[task] = tuple(TextileChoice(machine, mid, modes[mid].duration)
                                      for machine in machines for mid in mids if mid in machine_modes[machine])
        if not choices_by_task[task]: raise TextileInputError(f"Task {task!r} has no eligible machine/mode")

    products: dict[str, tuple[tuple[str, int], ...]] = {}
    for i, row in enumerate(raw["products"]):
        p = f"products[{i}]"; _keys(row, p, {"id", "tasks"}); name = _str(row["id"], p + ".id")
        if name in products: raise TextileInputError(f"Duplicate product: {name}")
        _shape(row["tasks"], p + ".tasks", list)
        if not row["tasks"]: raise TextileInputError(f"{p}.tasks must not be empty")
        requirements = []
        for k, task_row in enumerate(row["tasks"]):
            path = f"{p}.tasks[{k}]"; _keys(task_row, path, {"task", "runs"})
            task = _str(task_row["task"], path + ".task")
            if task not in task_modes: raise TextileInputError(f"{path} references unknown task {task!r}")
            requirements.append((task, _int(task_row["runs"], path + ".runs", 1, 1000)))
        _unique([task for task, _ in requirements], p + ".tasks")
        products[name] = tuple(requirements)
    if not products: raise TextileInputError("products must not be empty")

    orders, collisions = [], []
    for i, row in enumerate(raw["constraints"]):
        p = f"constraints[{i}]"; _keys(row, p, {"type", "parameter"})
        kind = _str(row["type"], p + ".type"); params = row["parameter"]
        if kind == "Order":
            _keys(params, p + ".parameter", {"first_task", "second_task"})
            a, b = _str(params["first_task"], p), _str(params["second_task"], p)
            orders.append((a, b) if order_interpretation == "json" else (b, a))
        elif kind == "Collision":
            _keys(params, p + ".parameter", {"task1", "task2"})
            a, b = _str(params["task1"], p), _str(params["task2"], p)
            collisions.append((a, b))
        else:
            raise TextileInputError(f"{p}: unsupported source constraint type {kind!r}; refusing to ignore it")
        if a not in task_modes or b not in task_modes or a == b:
            raise TextileInputError(f"{p}: constraint must reference two different known tasks")
    _unique(["\0".join(x) for x in orders], "Order constraints")
    _unique(["\0".join(sorted(x)) for x in collisions], "Collision constraints")

    sources = {}
    for i, row in enumerate(raw["energy_sources"]):
        p = f"energy_sources[{i}]"; _shape(row, p, dict)
        source_id = _str(row.get("id"), p + ".id")
        if source_id in sources: raise TextileInputError(f"Duplicate energy source: {source_id}")
        if source_id == "Socket Energy":
            _keys(row, p, {"id", "price"}); sources[source_id] = _vector(row["price"], p + ".price", horizon)
        elif source_id == "Solar":
            _keys(row, p, {"id", "availability"}); sources[source_id] = _vector(row["availability"], p + ".availability", horizon)
        else:
            raise TextileInputError(f"{p}: unsupported energy source {source_id!r}")
    if set(sources) != {"Socket Energy", "Solar"}:
        raise TextileInputError("Exactly one Socket Energy price and one Solar availability series are required")

    requests = []
    operations = []
    for ri, row in enumerate(raw["product_requests"]):
        p = f"product_requests[{ri}]"; _keys(row, p, {"product", "amount"}, {"deadline"})
        product = _str(row["product"], p + ".product")
        if product not in products: raise TextileInputError(f"{p}: unknown product {product!r}")
        amount = _int(row["amount"], p + ".amount", 1, 5000)
        deadline = _int(row["deadline"], p + ".deadline", 0, horizon) if "deadline" in row else None
        requests.append({"request_id": f"R{ri+1:03d}", "product": product, "amount": amount, "deadline": deadline})
        if len(operations) + amount * sum(runs for _, runs in products[product]) > 5000:
            raise TextileInputError("Expanded problem exceeds the supported limit of 5,000 task runs")
        for ui in range(amount):
            unit_id = f"R{ri+1:03d}-U{ui+1:04d}"
            unit_ops: list[TextileOperation] = []
            for ti, (task, runs) in enumerate(products[product]):
                for run in range(1, runs + 1):
                    oid = f"{unit_id}-T{ti+1:02d}-R{run:02d}"
                    unit_ops.append(TextileOperation(oid, unit_id, ri, ui, product, task, ti, run, deadline, choices_by_task[task]))
            # Repeated runs are interchangeable labels. Order their *starts*,
            # not their end-to-start execution, so independent repeated runs can
            # overlap if the selected unit policy allows it. Only explicit Order
            # pairs create true cross-task precedence.
            for op in unit_ops:
                previous = next((x.operation_id for x in unit_ops
                                 if x.task == op.task and x.run_index == op.run_index - 1), None)
                predecessors = []
                for first, second in orders:
                    if op.task == second:
                        predecessors.extend(x.operation_id for x in unit_ops if x.task == first)
                operations.append(replace(op, predecessors=tuple(dict.fromkeys(predecessors)), symmetry_predecessor=previous))
    if not operations: raise TextileInputError("product_requests must contain at least one requested task run")
    task_counts = {task: sum(op.task == task for op in operations) for task in task_modes}
    collision_expansion = sum(task_counts[a] * task_counts[b] for a, b in collisions)
    if collision_expansion > 100_000:
        raise TextileInputError("Collision expansion exceeds 100,000 task pairs; no constraint was skipped")
    # Detect cycles induced by uploaded order constraints for each product unit.
    pending = {op.operation_id: set(op.predecessors) for op in operations}
    while pending:
        ready = [oid for oid, pred in pending.items() if not pred]
        if not ready: raise TextileInputError("Order constraints create a cyclic task dependency")
        for oid in ready: pending.pop(oid)
        ready_set = set(ready)
        for pred in pending.values(): pred.difference_update(ready_set)
    unused = sorted(set(modes) - {mid for values in machine_modes.values() for mid in values})
    warnings = []
    if unused: warnings.append("Task modes with no eligible machine (not used): " + ", ".join(unused))
    if orders: warnings.append("JSON first/second naming and the accompanying article's order direction disagree for the published case; chosen interpretation is explicit.")
    return TextileInstance(cell_id, machines, modes, task_modes, machine_modes, products, tuple(requests),
                           tuple(operations), tuple(orders), tuple(collisions), horizon, leaps,
                           sources["Socket Energy"], sources["Solar"], order_interpretation, unit_exclusive,
                           sha256(raw_bytes).hexdigest(), tuple(warnings), stop_seconds)


def source_slot_label(slot: int, *, end: bool = False) -> str:
    """Published six-day calendar labels; a boundary finish is 23:00 previous day."""
    if slot < 0 or slot > 1152: return f"slot {slot}"
    days = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
    day, offset = divmod(slot, 192)
    if end and offset == 0 and slot > 0:
        day -= 1; offset = 192
    if day >= 6: return "Sat 23:00"
    minute = 7 * 60 + offset * 5
    return f"{days[day]} {minute // 60:02d}:{minute % 60:02d}"
