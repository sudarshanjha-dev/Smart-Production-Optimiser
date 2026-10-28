# Assumptions, input contract and limitations

## Time, orders and operations

- The factory clock starts at a user-selected **local date at 00:00**. Every release, due, start, finish and downtime field is a nonnegative integer **minute offset**, not a Unix timestamp. No timezone or daylight-saving conversion is applied.
- The sample starts on Monday `2026-11-02 00:00`; minute 480 is 08:00 that day and minute 1,920 is 08:00 the next day. The default horizon is 14 calendar days (20,160 minutes).
- Each order is one non-splittable batch of a single product. Every routing operation processes its full order quantity; yield loss, transfers and setup crews are not modeled. A routing is a linear, consecutive chain with no parallel operations.
- A selected machine executes fixed setup plus `minutes_per_unit × quantity` as one continuous, non-preemptive interval. Machine-specific setup and processing times are supported. **Sequence-dependent** setup is not implemented.
- Priority is an integer from 1 (lowest) to 5 (highest). Due dates can be later than the horizon, but must be no earlier than release. A late order has `completion > due`; tardiness is `max(0, completion - due)`.
- Cmax is the latest finish measured from the origin; it includes initial waiting, nights, weekends and maintenance. Active span is `max(finish) - min(start)` and is a different measure. Machine utilization is busy time divided by available time from origin through Cmax; it includes setup and, in revised schedules, aborted history.

## Calendar and resources

- A machine has **one same-day recurring shift** and a set of working weekdays (`0` = Monday, `6` = Sunday). Shift end can be 1,440 (midnight). A cross-midnight shift or multiple shifts in one day cannot be entered directly. Adjacent 24-hour shift windows are treated as continuous availability.
- Planned downtime and simulated breakdowns subtract from those shifts. Overlapping or adjacent blocked periods are merged. Every operation must fit inside a single resulting continuous window. No overtime is modeled.
- Each operation lists one or more eligible machines, all in the **same resource group**. The CP-SAT model chooses a machine and respects its duration; the same-group restriction makes the aggregate capacity planning relaxation meaningful.
- There is no operator, tool, material timing, transport, parallel crew or buffer-capacity constraint. No machine is assumed to have been deployed or measured in a real factory.

## Production-planning boundary

- The planner uses one shared stock of abstract raw-material units available at the start of the horizon and aggregate machine-group minutes. It minimizes unit production cost plus product shortage penalty multiplied by order priority. It may partially fulfill an order or set it to zero; no inventory or revenue is modeled.
- Minimum eligible unit time and minimum eligible setup are used **independently** per operation in the aggregate capacity load. These are lower bounds and can come from different machines. The planner ignores individual due dates and shift fragmentation. Passing a plan to CP-SAT recalculates exact batch-dependent durations, but **does not guarantee a feasible schedule**.
- Urgent orders are inserted directly into scheduling, not back through the raw-material planner. The operator must confirm stock separately.

## Disruption policy

- Breakdown starts at the decision minute, lasts until the specified end and is half-open. Directly affected operations are those in the original schedule overlapping the outage.
- Completed operations and operations already in progress on other machines are fixed. An operation starting exactly at the decision instant is treated as **not yet started**. If a broken machine has an operation already in progress, the already-spent segment is recorded as aborted, all partial progress is discarded, and the operation restarts with full setup and processing on that same machine after repair. This includes failures during setup. Predecessors and successor constraints remain in force.
- A newly urgent order is released at the decision time. The existing schedule is protected by explicit start-shift and machine-change penalties, not by a guarantee that no future operation changes.
- The UI applies one scenario to a selected original schedule. It does not apply a second disruption to an already revised schedule with aborted history, and it does not track real machine execution automatically.

## CSV input schema

Use UTF-8 CSV with headers. Upload **orders, machines, products and routings together**; downtime is optional. Extra columns are ignored. IDs are unique within each table; order IDs cannot contain `::` because that string separates the generated operation ID from its sequence. Example templates are in `data/` and downloadable in Factory Setup.

### `orders.csv`

| Column | Meaning |
|---|---|
| `order_id` | Unique nonblank order ID. |
| `product_id` | Existing product ID. |
| `quantity` | Positive integer demand. |
| `release_minute` | Nonnegative integer offset from origin. |
| `due_minute` | Integer offset, at least the release. |
| `priority` | Integer 1–5; larger means higher priority. |

### `machines.csv`

| Column | Meaning |
|---|---|
| `machine_id` | Unique nonblank machine ID. |
| `machine_name` | Display name. |
| `resource_group` | Aggregate capacity group; all alternatives for a step share it. |
| `shift_start_minute` | Integer minute of day, 0–1439. |
| `shift_end_minute` | Integer minute of day, strictly after start and at most 1440. |
| `working_days` | Pipe-separated weekday digits, e.g. `0\|1\|2\|3\|4`. |

### `products.csv`

| Column | Meaning |
|---|---|
| `product_id`, `product_name` | Unique product ID and display name. |
| `unit_cost` | Nonnegative unit production cost. |
| `shortage_penalty` | Nonnegative cost per unfulfilled unit, multiplied by order priority. |
| `material_per_unit` | Nonnegative integer units from the shared material stock. |

### `routings.csv`

One row for **each eligible machine** for an operation. For a product, sequence numbers must be consecutive starting at 1. All rows for the same `(product_id, operation_sequence)` use the same operation name and resource group; a machine appears at most once in that step.

| Column | Meaning |
|---|---|
| `product_id` | Existing product. |
| `operation_sequence` | Positive consecutive sequence number. |
| `operation_name` | Name shared by alternatives. |
| `machine_id` | Eligible machine ID. |
| `minutes_per_unit` | Positive integer processing time on that machine. |
| `setup_minutes` | Nonnegative integer fixed setup time for the batch on that machine. |

Operation IDs and predecessor IDs are generated, e.g. `ORD-001::02` follows `ORD-001::01`. An operation's required duration is computed separately for each eligible machine.

### `downtimes.csv` (optional)

| Column | Meaning |
|---|---|
| `machine_id` | Existing machine. |
| `start_minute`, `end_minute` | Nonnegative start and later end, offset from origin. Intervals outside the horizon are ignored after clipping. |
| `reason` | Nonblank label, e.g. planned maintenance. |

## Output and persistence

The machine-wise schedule CSV records operation/order/product IDs, sequence, predecessor, quantity, machine, start, finish, fixed setup, processing duration, release, due, priority and segment type. A breakdown's aborted segment is maintained separately from required operations; a revised schedule CSV and history can be inspected in the app. Sample exports are in `results/`.

UI state is held only in the current Streamlit session. User-generated schedules/plans are not automatically written to a database; download the CSVs to persist them. Uploaded files are validated for schema, types, references and basic range constraints, but this is not a multi-user, authenticated or safety-certified manufacturing control system.
