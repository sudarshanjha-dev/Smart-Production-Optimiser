"""Regenerate the example CSVs. Values are synthetic, not factory measurements."""
from pathlib import Path
import random
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

machines = [
    ("M01", "Saw 1", "CUTTING", 480, 1020, "0|1|2|3|4"),
    ("M02", "Saw 2", "CUTTING", 510, 990, "0|1|2|3|4"),
    ("M03", "CNC 1", "MACHINING", 480, 1020, "0|1|2|3|4"),
    ("M04", "CNC 2", "MACHINING", 540, 1020, "0|1|2|3|4"),
    ("M05", "Finishing cell", "FINISHING", 480, 960, "0|1|2|3|4"),
    ("M06", "Assembly cell", "ASSEMBLY", 480, 1020, "0|1|2|3|4"),
]
pd.DataFrame(machines, columns=["machine_id", "machine_name", "resource_group", "shift_start_minute", "shift_end_minute", "working_days"]).to_csv(DATA / "machines.csv", index=False)

products = [
    ("P-A", "Mounting bracket", 18, 95, 2),
    ("P-B", "Drive shaft", 25, 125, 3),
    ("P-C", "Pump housing", 32, 150, 4),
    ("P-D", "Hinge pin", 12, 75, 1),
    ("P-E", "Gear blank", 24, 120, 3),
    ("P-F", "Fixture plate", 16, 90, 2),
]
pd.DataFrame(products, columns=["product_id", "product_name", "unit_cost", "shortage_penalty", "material_per_unit"]).to_csv(DATA / "products.csv", index=False)

# One row per eligible machine: unit processing time is machine-specific.
recipes = {
    "P-A": [("Cutting", [("M01", 2, 8), ("M02", 3, 6)]), ("Milling", [("M03", 4, 14), ("M04", 5, 10)]), ("Deburring", [("M05", 2, 6)]), ("Assembly", [("M06", 3, 8)])],
    "P-B": [("Cutting", [("M01", 3, 8), ("M02", 2, 10)]), ("Turning", [("M03", 4, 12), ("M04", 5, 11)]), ("Grinding", [("M05", 3, 8)]), ("Final assembly", [("M06", 2, 7)])],
    "P-C": [("Cutting", [("M01", 4, 10), ("M02", 5, 7)]), ("Milling", [("M03", 6, 16), ("M04", 5, 16)]), ("Drilling", [("M05", 3, 9)]), ("Assembly", [("M06", 4, 10)])],
    "P-D": [("Cutting", [("M01", 2, 6), ("M02", 2, 7)]), ("Turning", [("M03", 3, 10), ("M04", 4, 8)]), ("Finishing", [("M05", 2, 5)]), ("Packing", [("M06", 2, 6)])],
    "P-E": [("Cutting", [("M01", 3, 9), ("M02", 3, 8)]), ("Milling", [("M03", 5, 15), ("M04", 4, 17)]), ("Deburring", [("M05", 3, 7)]), ("Assembly", [("M06", 3, 9)])],
    "P-F": [("Cutting", [("M01", 2, 7), ("M02", 3, 6)]), ("CNC drilling", [("M03", 3, 12), ("M04", 4, 8)]), ("Assembly", [("M06", 3, 8)])],
}
rows = []
for pid, operations in recipes.items():
    for seq, (name, alternatives) in enumerate(operations, 1):
        for machine, minutes, setup in alternatives:
            rows.append((pid, seq, name, machine, minutes, setup))
pd.DataFrame(rows, columns=["product_id", "operation_sequence", "operation_name", "machine_id", "minutes_per_unit", "setup_minutes"]).to_csv(DATA / "routings.csv", index=False)

rng = random.Random(41)
orders = []
product_ids = [p[0] for p in products]
for i in range(1, 25):
    pid = product_ids[(i - 1) % len(product_ids)]
    qty = rng.randint(6, 17)
    release = 0 if i <= 18 else 1440 + 480
    # Some orders have deliberately tight same-day deadlines.
    due_day = max(0 if i <= 18 else 1, rng.choice([0, 0, 1, 1, 2, 3]))
    due = due_day * 1440 + 960
    priority = rng.choice([1, 1, 2, 2, 3])
    orders.append((f"ORD-{i:03d}", pid, qty, release, due, priority))
pd.DataFrame(orders, columns=["order_id", "product_id", "quantity", "release_minute", "due_minute", "priority"]).to_csv(DATA / "orders.csv", index=False)

pd.DataFrame([
    ("M03", 1440 + 720, 1440 + 810, "Preventive maintenance"),
    ("M06", 2 * 1440 + 780, 2 * 1440 + 840, "Assembly cell maintenance"),
], columns=["machine_id", "start_minute", "end_minute", "reason"]).to_csv(DATA / "downtimes.csv", index=False)
print(f"Wrote deterministic sample data to {DATA}")
