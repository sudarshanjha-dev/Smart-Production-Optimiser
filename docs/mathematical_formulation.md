# Mathematical formulation

This project deliberately separates **how much to make** from **where and when to make it**. The first model is an aggregate mixed-integer linear program (MILP) solved by PuLP/CBC. The second is a flexible job-shop constraint model solved by OR-Tools CP-SAT. All data in the repository are synthetic.

## 1. Aggregate production quantity planning

### Sets, data and variables

- `o ∈ O`: customer orders; `p(o)` is the product, `d_o` its demand and `w_o ∈ {1,…,5}` its priority.
- `g ∈ G`: resource groups such as cutting or machining. Every eligible machine for a particular routing step belongs to the same group.
- `c_p`: unit production cost; `π_p`: shortage penalty per unit; `r_p`: material units consumed per unit produced; `R`: total available material.
- `A_g`: aggregate available machine minutes for the group over the horizon, including shifts and excluding downtime; `α ∈ (0,1]`: selected capacity fraction.
- `a_og`: sum, over order `o`'s operations in group `g`, of the **smallest** per-unit processing time among eligible machines.
- `b_og`: corresponding sum of the **smallest** fixed setup times. The machines giving the two minima need not be the same.
- `q_o`: integer quantity to make; `u_o`: integer unmet demand; `z_o`: binary indicator that any of order `o` is produced.

### Model

```text
minimize  Σ_o [ c_p(o) q_o + π_p(o) w_o u_o ]

subject to
  q_o + u_o = d_o                            for each order o
  z_o ≤ q_o ≤ d_o z_o                        for each order o
  Σ_o [a_og q_o + b_og z_o] ≤ α A_g          for each resource group g
  Σ_o r_p(o) q_o ≤ R                         shared material limit
  q_o, u_o nonnegative integers; z_o binary.
```

The implementation can substitute `u_o = d_o - q_o` rather than create it as a separate solver variable. This is a one-horizon model: it has no inventory balance, no period-by-period arrivals, and no due-date constraints. Costs are arbitrary cost units. The group constraint is an **optimistic lower bound** on actual machine time. Even an optimal aggregate plan can be impossible to schedule because of alternative-machine trade-offs, precedence, shift fragmentation, release times or due dates. There is a test explicitly demonstrating this boundary.

The integration step replaces each order's demand quantity by `q_o`; orders with `q_o = 0` are omitted. Every required operation for a remaining order is then built using that planned quantity. The unchanged shortage is reported in the planning table rather than silently passed as scheduled production.

## 2. Detailed flexible job-shop scheduling

### Sets and data

- `i ∈ I`: operations; each belongs to one order `o(i)` and has a predecessor if it is not the first routing step.
- `M_i`: eligible machines; `q_o`: fixed scheduled batch size (original demand or planned quantity).
- `p_im = setup_im + unit_minutes_im × q_o(i)`: total non-preemptive setup-plus-processing duration on eligible machine `m`.
- `r_o`, `d_o`, `w_o`: order release, due minute and priority. `H` is the horizon in minutes.
- Each machine's available windows are derived from its weekday shift, planned maintenance and any breakdown; unavailable intervals are merged into a non-overlapping complement of those windows.

### Decision variables

- `x_im ∈ {0,1}`: operation `i` uses eligible machine `m`.
- `S_i`, `F_i`: operation start and finish, in integer minutes.
- `C_o`: completion of the last operation of order `o`; `T_o ≥ 0`: its tardiness.
- `Cmax`: latest order completion from the origin.

### Core constraints

```text
Σ_(m∈M_i) x_im = 1                         for every operation i
x_im = 1  ⇒  F_i = S_i + p_im             selected machine determines duration
S_i ≥ r_o(i)                               no operation before order release
S_successor ≥ F_predecessor                routing precedence
C_o = F_last(o)
T_o = max(0, C_o − d_o)
Cmax = max_o C_o
0 ≤ S_i, F_i, Cmax ≤ H;  x_im binary.
```

For each `(i,m)` the model creates an **optional interval** `[S_i,F_i)` of duration `p_im` that is present exactly when `x_im=1`. On each machine, CP-SAT's `NoOverlap` covers those optional intervals **and fixed intervals for off-shift time, planned maintenance and breakdowns**. Therefore no two assigned operations overlap and each entire setup-plus-processing interval lies in a continuous available window. Intervals touching at a boundary do not overlap.

Conceptually, for two operations `i,j` assigned to the same machine, this enforces the disjunction `F_i ≤ S_j OR F_j ≤ S_i`; CP-SAT implements it with optional intervals rather than a big-M ordering formulation. Fixed setup is included in the operation interval. Setup does **not** depend on the product previously run on that machine.

### Objective selection

1. **Minimum makespan:** `min Cmax`. This may sacrifice individual delivery dates.
2. **Minimum weighted tardiness with makespan tie-break:**

   ```text
   min (H + 1) × Σ_o (w_o T_o) + Cmax
   ```

   Since `0 ≤ Cmax ≤ H` and all times/weights are integer, improving weighted tardiness by one minute dominates every possible Cmax change. This is an exact lexicographic objective, not merely a convenient weighted average. The raw objective/bound in the UI has these composite units; the displayed tardiness and Cmax are recomputed from the schedule.

`OPTIMAL` means CP-SAT proved the selected objective; `FEASIBLE` is a valid incumbent without an optimality proof; `INFEASIBLE` is a proof for the specified input/horizon; `UNKNOWN` means no conclusion. `MODEL_INVALID` is a model error. A dispatch-rule failure proves nothing about feasibility.

## 3. Dispatch baselines

FIFO ranks precedence-ready operations by order release and input order; EDD ranks by order due date, then release and input order; SPT ranks by the minimum eligible total duration, then release and input order. A serial schedule-generation procedure selects the top-ranked ready operation, finds the earliest fitting continuous window for each eligible machine, and assigns it to the earliest-finishing option. It reserves machine time and repeats. The result is separately validated. If the greedy procedure cannot place an operation, it reports `HEURISTIC_FAILED`, even though a different ordering might be feasible.

## 4. Dynamic rescheduling

At a decision time `t`, completed operations (`F_i ≤ t`) are fixed to their actual machine, start and finish. Operations with `S_i < t < F_i` are also fixed, except a running operation on the failed machine. Not-yet-started operations receive `S_i ≥ t`. The breakdown adds `[t, repair_end)` to the machine's unavailable intervals.

If the broken machine is processing an operation at `t`, the segment `[old_S_i,t)` is recorded as **aborted historical work** and blocks that machine in the new model. The operation is rescheduled with its **entire original setup and processing duration**, constrained to the same machine and `S_i ≥ repair_end`. No partial credit is taken. Successors wait for the restarted operation to finish. Other machines' running operations remain fixed. If no operation was running on the failed machine, there is no aborted segment.

For an urgent order, its release is `t` and its routing is added; completed and running original operations stay fixed. There is no automatic material-availability re-plan for that order.

Both scenarios minimize the following explicit **weighted trade-off**, not a lexicographic objective:

```text
10 × Σ_o (w_o T_o)
+ Σ_(old operations i) |new_S_i − old_S_i|
+ 120 × Σ_(old operations i) 1[new machine_i ≠ old machine_i].
```

The first term addresses delivery performance, the second penalizes schedule movement in minutes, and the third penalizes a reassignment as if it cost 120 minutes of movement. Weights are illustrative, not empirically calibrated. New urgent operations have no old start or machine and therefore no stability term. Different weights can yield different managerial trade-offs. The model re-solves all operations with the fixed decisions and new constraints; the chart is built from the new solution.

## 5. Shift-capacity what-if

An expansion changes one machine's shift end for each working day, then solves the full schedule again before execution. Additional available minutes account for existing downtime. The illustrative cost calculation is:

```text
extra capacity cost = added available minutes / 60 × cost per added hour
estimated delay saving = (old weighted tardiness − new weighted tardiness)
                         × cost per weighted tardy minute
estimated net = estimated delay saving − extra capacity cost.
```

This excludes all other costs and benefits. Time-limited feasible incumbents do not prove the maximum benefit obtainable from expansion.
