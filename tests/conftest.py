import pandas as pd
import pytest
from src.data_loader import make_factory

@pytest.fixture
def tiny_factory():
    """Two jobs, 2->3 minute route: manual optimum is Cmax = 8 minutes."""
    return make_factory(
        orders=pd.DataFrame([
            ["J1", "P", 1, 0, 9, 1], ["J2", "P", 1, 0, 9, 2]],
            columns=["order_id", "product_id", "quantity", "release_minute", "due_minute", "priority"]),
        machines=pd.DataFrame([
            ["A", "A", "CUT", 0, 1440, "0|1|2|3|4|5|6"],
            ["B", "B", "PACK", 0, 1440, "0|1|2|3|4|5|6"]],
            columns=["machine_id", "machine_name", "resource_group", "shift_start_minute", "shift_end_minute", "working_days"]),
        products=pd.DataFrame([["P", "Part", 1, 20, 1]],
            columns=["product_id", "product_name", "unit_cost", "shortage_penalty", "material_per_unit"]),
        routings=pd.DataFrame([["P", 1, "Cut", "A", 2, 0], ["P", 2, "Pack", "B", 3, 0]],
            columns=["product_id", "operation_sequence", "operation_name", "machine_id", "minutes_per_unit", "setup_minutes"]),
        horizon=100)


@pytest.fixture
def textile_fixture():
    return {
        'cells': [{'id': 'cell', 'machines': ['M1', 'M2']}],
        'task_modes': [{'id': 'X1', 'power': [10, 10]}, {'id': 'Y1', 'power': [4, 4]}],
        'tasks': [{'id': 'X', 'task_modes': ['X1']}, {'id': 'Y', 'task_modes': ['Y1']}],
        'machines': [{'id': 'M1', 'task_modes': ['X1']}, {'id': 'M2', 'task_modes': ['Y1']}],
        'products': [{'id': 'P', 'tasks': [{'task': 'X', 'runs': 1}, {'task': 'Y', 'runs': 1}]}],
        'constraints': [{'type': 'Order', 'parameter': {'first_task': 'X', 'second_task': 'Y'}},
                        {'type': 'Collision', 'parameter': {'task1': 'X', 'task2': 'Y'}}],
        'energy_sources': [{'id': 'Socket Energy', 'price': [0.5]*10}, {'id': 'Solar', 'availability': [0]*10}],
        'product_requests': [{'product': 'P', 'amount': 1, 'deadline': 8}],
        'configuration': {'time_window': 10, 'time_leap': [5], 'stop_condition': {'seconds': 10}},
    }
