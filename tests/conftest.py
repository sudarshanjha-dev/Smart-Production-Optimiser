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
