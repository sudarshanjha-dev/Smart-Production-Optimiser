# Portfolio and interview notes

## Two-line résumé description

- Built a Python production-planning and flexible job-shop scheduling tool using PuLP/CBC and OR-Tools CP-SAT, with machine eligibility, routing precedence, shifts, maintenance and priority-weighted due dates.
- Implemented dispatch-rule baselines, interactive machine Gantt charts and disruption re-optimization for breakdowns and urgent orders; validated schedules with automated feasibility tests on synthetic manufacturing data.

## Concise Operations Intern interview explanation

“I modeled a small synthetic factory where orders compete for shared machines. An aggregate MILP first chooses how much of each order to make given material and capacity limits. A separate CP-SAT model assigns each routed operation to an eligible machine and a start time while respecting shifts, maintenance and precedence. I compare FIFO and EDD against makespan and priority-weighted tardiness objectives, visualize the actual schedule, and re-solve after a breakdown or urgent arrival. I verify feasibility independently and distinguish a feasible incumbent from a proven optimum. The data and results are synthetic; this was not a factory deployment.”

## Five technical interview questions and answers

**1. Why separate production planning from machine scheduling?**  
The planning MILP allocates quantities across orders under aggregate material and resource-group capacity. Scheduling then makes detailed machine and time decisions. Aggregate capacity ignores sequencing and calendar fragmentation, so even an optimal quantity plan can be unschedulable; the project explicitly checks this second stage.

**2. How does the model prevent two jobs using a machine simultaneously?**  
For every eligible operation–machine pair, CP-SAT creates an optional interval controlled by an assignment Boolean. Exactly one machine is selected per operation. A `NoOverlap` constraint for each machine includes all its optional operation intervals plus fixed off-shift and downtime intervals.

**3. How are different machine speeds and setup times represented?**  
Each eligible machine has its own `minutes_per_unit` and fixed batch setup. The selected interval duration is `setup + planned_quantity × minutes_per_unit`. Setup occupies the machine and must fit inside an available window. The current model does not implement sequence-dependent changeover.

**4. What happens if a breakdown interrupts a job?**  
The executed partial segment is preserved as historical occupied time but earns no production credit. The full setup and processing restart on the same machine after repair. Completed operations and unaffected in-progress operations keep their machine, start and finish. The remaining operations are re-optimized with the outage and stability penalties.

**5. What is the difference between FEASIBLE and OPTIMAL?**  
`FEASIBLE` means a valid schedule was found but the solver did not prove it is best before stopping. `OPTIMAL` proves the objective is best within the model. `INFEASIBLE` proves no solution exists under the modeled constraints and horizon; a dispatch rule's failure or `UNKNOWN` does not.

## How Operations Research is applied

The project translates a manufacturing decision into variables, an objective and constraints. The MILP allocates scarce material and aggregate capacity across demand. The CP-SAT flexible job-shop model selects machine assignments and operation times subject to precedence, resource exclusivity and calendars. Alternative objectives expose a genuine operations trade-off between finishing all work quickly and protecting high-priority due dates. Scenario re-optimization evaluates a disruption or a capacity change without claiming real-world savings.
