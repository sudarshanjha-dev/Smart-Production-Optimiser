from src.data_loader import load_sample, build_operations
from src.dispatching_rules import dispatch_schedule
from src.schedule_validator import validate_schedule
from src.scheduling_model import solve_schedule


def test_manual_optimum(tiny_factory):
    r = solve_schedule(tiny_factory, time_limit=5, workers=1)
    assert r.status == "OPTIMAL"
    assert r.schedule.finish.max() == 8
    assert r.objective_value == r.best_bound == 8
    assert validate_schedule(tiny_factory, r.schedule) == []


def test_sample_baselines_are_complete_and_valid():
    f = load_sample()
    assert (len(f.orders), len(f.machines), len(f.products), len(build_operations(f))) == (24, 6, 6, 92)
    for rule in ("FIFO", "EDD", "SPT"):
        r = dispatch_schedule(f, rule)
        assert r.status == "HEURISTIC"
        assert len(r.schedule) == 92
        assert validate_schedule(f, r.schedule) == []


def test_infeasible_not_reported_as_feasible(tiny_factory):
    f = tiny_factory.replace(horizon=4)
    r = solve_schedule(f, time_limit=3, workers=1)
    assert r.status == "INFEASIBLE"
    assert not r.has_schedule
    assert r.schedule.empty
    baseline = dispatch_schedule(f, "FIFO")
    assert baseline.status == "HEURISTIC_FAILED"  # not a proof of infeasibility
