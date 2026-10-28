# Zenodo textile case-study data and interpretation

## Provenance and license

Bruno Mota, Luis Gomes, Pedro Faria, Carlos Ramos, and Zita Vale, *Production line dataset for task scheduling and energy optimization – Schedule Optimization*, 2020, version 0.1. [Zenodo record 4106746 / DOI 10.5281/zenodo.4106746](https://doi.org/10.5281/zenodo.4106746). The record declares the **MIT License**; the original input and license/attribution are included in `data/textile/`. Related article: Mota et al., *Energies* 14(2), 462 (2021), [DOI 10.3390/en14020462](https://doi.org/10.3390/en14020462).

The bundled unaltered input has SHA-256 `5cecb2eb95437d6b789726f302860cefb446731af9eadba2a8379af5644ed169`, Zenodo MD5 `b9be4a13a865a2364651259b562b81a1`. The adapter verifies this file and loads it without network access; if it is absent, it downloads and checksum-verifies the pinned Zenodo input, cached once per process. The UI also has an explicit verified refresh button and permits a compatible user upload. An upload is separately validated and identified by its own SHA-256; it is **not** represented as the published dataset.

This is a real case-study **input**, not a record that our generated schedule was actually executed. No machine breakdowns, urgent orders, release dates, extra deadlines, product prices, material levels, inventory costs, setup times, or historical events are manufactured for it.

## Input schema and units

All listed fields are required except `deadline`. Unknown fields, extra energy sources, unknown constraint types/references, duplicate IDs or duplicate JSON keys, malformed numbers, cyclic orders, inconsistent series lengths and invalid times are rejected rather than ignored. The parser currently handles one cell, at most 5,000 expanded runs and 100,000 collision pairs; it does not implement other paper-domain features absent from this file.

| JSON field | Meaning and handling |
|---|---|
| `cells[].id` | Cell identifier; input has one cell, `factory`. |
| `cells[].machines[]` | Exact set of machine identifiers belonging to the cell. |
| `task_modes[].id` | Mode identifier, owned by exactly one task. |
| `task_modes[].power[]` | One nonnegative source profile value per consecutive **five-minute working slot**. The array length is the non-interruptible duration. Despite the key name `power`, the paper describes energy **per period** with Wh-based units; the inconsistency below prevents conversion claims. |
| `tasks[].id` | Task-type identifier. |
| `tasks[].task_modes[]` | Modes allowed for that task. A mode is usable only if a machine also declares it. |
| `machines[].id` | Machine identifier, exclusive to at most one task at a time. |
| `machines[].task_modes[]` | Modes the machine can execute. |
| `products[].id` | Product-type identifier. Whitespace and accents are preserved exactly. |
| `products[].tasks[].task` | Required task type, not an automatic routing precedence. |
| `products[].tasks[].runs` | Number of separate executions of the task required per requested product unit. |
| `constraints[].type`, `parameter.first_task`, `parameter.second_task` | `Order`: per-unit end-before-start constraint, with direction explicitly selected; source scope and direction require interpretation as described below. |
| `constraints[].type`, `parameter.task1`, `parameter.task2` | `Collision`: the two task types cannot overlap anywhere in this shared cell. |
| `energy_sources[id="Socket Energy"].price[]` | One nonnegative price coefficient per working slot; currency and any physical conversion are not verified. |
| `energy_sources[id="Solar"].availability[]` | One nonnegative source solar availability value per slot, in raw source units. |
| `product_requests[].product` | Reference to an existing product type. |
| `product_requests[].amount` | Number of product units for that request. Each unit has all specified task runs. |
| `product_requests[].deadline` | Optional integer slot boundary by which **all** runs of each unit in the request must end. The dataset has one request with deadline 960; no deadlines are invented for the rest. |
| `configuration.time_window` | 1,152 working slots = 5,760 working minutes, six 16-hour days. |
| `configuration.time_leap[]` | Noninterruptible tasks may start or end at, but not cross, boundaries 192, 384, 576, 768, 960. |
| `configuration.stop_condition.seconds` | 7,200 seconds, an original algorithm parameter, not a constraint on feasible schedules. The UI sets its own CP-SAT search limit. |

Working intervals are half-open `[start_slot, end_slot)`, zero-based. Slots are compressed across breaks: `end_slot=192` is Monday 23:00; `start_slot=192` is Tuesday 07:00. Similarly `end_slot=960` is Friday 23:00 and `start_slot=960` is Saturday 07:00. Six working days are Monday–Saturday, 07:00–23:00. No actual calendar date or timezone is supplied. These weekday labels are only applied to the verified published input; uploaded data is shown in generic slots. CSVs retain the integer slots and selected interpretation.

## Modes and compatibility in the published input

Each listed machine-mode pair is an alternative; a task is assigned to exactly one pair. Profile sums below are raw source values, not verified kWh.

| Task | Input mode | Eligible machine(s) | Slots | Minutes | Profile sum (raw) |
|---|---|---|---:|---:|---:|
| Ironing | Ironing TM1 | MAQ120 | 9 | 45 | 3,215 |
| Ironing | Ironing TM3 | MAQ119 | 9 | 45 | 5,985 |
| Ironing | Ironing TM4 | MAQ118 | 12 | 60 | 9,631 |
| Harden[0.5] | Harden[0.5] TM1 | MAQ119 | 12 | 60 | 14,479 |
| Harden[0.5] | Harden[0.5] TM4 | MAQ118 | 5 | 25 | 1,578 |
| Harden[1] | Harden[1] TM1 | MAQ119 | 16 | 80 | 2,418 |
| Harden[1] | Harden[1] TM2 | **none** | 5 | 25 | 5,852 |
| Harden[1] | Harden[1] TM5 | MAQ118 | 9 | 45 | 12,085 |
| Harden[1.5] | Harden[1.5] TM1 | MAQ119 | 25 | 125 | 19,185 |
| Harden[1.5] | Harden[1.5] TM3 | MAQ118 | 15 | 75 | 17,554 |
| Harden[2] | Harden[2] TM1 | MAQ118 | 23 | 115 | 18,605 |
| Sublimation | Sublimation TM3 | MAQ120 | 4 | 20 | 1,861 |
| Anti-Shrinkage | Anti-Shrinkage TM2 | MAQ120 | 7 | 35 | 1,679 |

`Harden[1] TM2` is declared by the task but no machine declares it; the adapter displays a warning and never assigns it. It does not discard other eligible alternatives.

## Products and quantities

There are 14 product types, 15 request rows, 132 product units and 275 task runs. The table preserves the source product requirements; order in the list is not assumed to be an execution route.

| Product | Required task runs per unit | Requested units |
|---|---|---:|
| WOVEN LABEL OURELA FABRIC | Ironing × 1, Harden[1] × 2, Harden[0.5] × 1 | 13 |
| ESTORE RIBBON | Ironing × 3 | 6 |
| WOVEN LABEL OURELA CUT | Ironing × 3, Harden[0.5] × 1, Harden[1] × 2, Harden[1.5] × 1 | 5 |
| GORGORÃO RIBBON | Ironing × 1 | 13 |
| GORGORÃO RIBBON W/ INSCR | Ironing × 1 | 5 |
| TAFFETA EMBLEM | Harden[1] × 1 | 10 |
| PRINTED RIBBON | Sublimation × 1, Anti-Shrinkage × 1 | 30 |
| ELASTIC W/ INSCR | Ironing × 1, Anti-Shrinkage × 2, Harden[0.5] × 1 | 3 |
| ROK ELASTIC | Harden[2] × 1, Harden[1.5] × 1 | 3 |
| SMOOTH STRAP(A) | Ironing × 1 | 4 |
| BRAIDED ELASTIC | Anti-Shrinkage × 1 | 15 |
| PRINTED RIBBON  PES | Sublimation × 1 | 10 |
| SMOOTH ELASTIC(A) | Harden[0.5] × 1 | 5 |
| STRAP W/ STRIPES | Harden[1] × 2, Anti-Shrinkage × 1 | 10 |

`ELASTIC W/ INSCR` appears in two separate request rows: two units with no deadline and one unit with deadline 960. Expanded operations are Ironing 71, Harden[1] 66, Anti-Shrinkage 61, Sublimation 40, Harden[0.5] 26, Harden[1.5] 8 and Harden[2] 3.

## Ambiguities and conservative choices

1. **Direction:** the JSON names `first_task=Harden[1.5]` and `second_task=Harden[2]`; the 2021 article says Harden[2] precedes Harden[1.5]. The selector supports both, defaulting to the JSON-name reading. The source doesn't conclusively specify assignment to individual expanded units, so the implementation explicitly assumes the rule applies between matching task types **within each product unit**, and makes all runs of the first task finish before any run of the second. No sequence is inferred from the product array.
2. **Same-unit overlap:** the default conservative policy treats a product unit as an exclusive resource. The alternative allows independent requirements of one unit to overlap while retaining machine no-overlap, explicit per-unit task order and cross-task collision. The companion output statistics workbook groups 275 rows under 132 `P...` product identifiers and contains four pairs of overlapping rows with the same identifier. These identifiers appear to represent units, but the physical interpretation is not independently confirmed. Identical repeated runs use start-order label symmetry only; this does **not** prevent overlap in the permissive policy.
3. **Energy:** the article specifies energy per period with Wh-based units and describes peak PV capacity of 3 kW, yet the input's solar `availability` peaks at 2,749.2 per five-minute slot. If taken literally as Wh per five-minute slot this corresponds to about 33 kW, inconsistent with the description. Therefore raw profile sums and `sum(max(0, total_profile[t] - solar[t]) * socket_price[t])` are reported as **source-unit scores**; no verified kWh, currency, physical savings, or grid-cost optimum is claimed. The optional profile objective minimizes selected profile sums, not the time-dependent source-style score.

## Published output is a reference, not the benchmark

The Zenodo output JSON records score `36.41559324199997`; recomputing the source-style score from its machine-energy arrays yields `36.415593242`. Six output `task_mode` identifiers are absent from the input: `Anti-Shrinkage TM1`, `Harden[0.5] TM2`, `Harden[1.5] TM2`, `Harden[1] TM3`, `Ironing TM2`, `Sublimation TM1`. The statistics workbook has product identifiers and 275 task rows; matching machine, task, duration and machine-profile samples identifies a unique input mode for every row, but the JSON identifiers themselves are not directly compatible. The workbook's three ROK ELASTIC product IDs exhibit the JSON-name direction, not the paper direction. Four same-product-ID overlaps violate our conservative unit-exclusivity policy, and the workbook does not unambiguously map its product IDs to the two original `ELASTIC W/ INSCR` request rows. Consequently, this output is **not an equal-constraint verified benchmark** for our default model and is not called an optimum.

To reproduce the output/workbook audit (downloads 1.35 MB of references to a temporary directory and verifies their MD5; no extra library required):

```bash
python scripts/audit_textile_reference.py
# or use already-downloaded, checksummed files:
python scripts/audit_textile_reference.py --reference-dir /path/to/zenodo-files
```

The workbook is not bundled because it is not required to run the application. The unavailable legacy SPEAR API is not a dependency.
