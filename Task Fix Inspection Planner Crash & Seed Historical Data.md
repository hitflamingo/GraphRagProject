# Task: Fix Inspection Planner Crash & Seed Historical Data

## 1. Context

We are upgrading the system to "Phase 2" (Intelligent Inspection). Currently, we are facing two issues:

1. **Critical Crash**: `inspection_planner.py` fails with `TypeError: unsupported operand type(s) for +: 'int' and 'NoneType'` when a feature has no tolerance defined in the Excel file.
2. **Missing Data**: The `RiskMiner` is querying for `DefectRecord` nodes in Neo4j, but these do not exist yet, causing Neo4j warnings and preventing the "Smart Planning" logic from triggering.

------

## 2. Action Items

### Step 1: Fix `TypeError` in `src/inspection_planner.py`

**Objective**: Add defensive coding to handle `None` values for tolerances.

**Instructions for Cursor**:

- Open `src/inspection_planner.py`.
- Locate the function `_compose_inspection_item`.
- Replace the logic where `upper_bound` and `lower_bound` are calculated.
- **Logic Change**: Only perform addition if `tol_upper` and `tol_lower` are NOT None. If they are None, set a fallback description.

**Reference Code**:

```python
def _compose_inspection_item(feature_context: Dict, decision: Dict, risk_context: Dict) -> Dict:
    # ... (existing setup code) ...
    
    target = feature_context.get('target_value')
    unit = feature_context.get('unit', 'mm')
    
    # Safe extraction
    tolerance = feature_context.get('tolerance') or {}
    tol_upper = tolerance.get('upper')
    tol_lower = tolerance.get('lower')

    # FIX: Check for None before arithmetic
    if target is not None and tol_upper is not None and tol_lower is not None:
        try:
            upper_bound = target + float(tol_upper)
            lower_bound = target + float(tol_lower)
            acceptance_criteria = f"{lower_bound:.2f} ~ {upper_bound:.2f} {unit}"
        except (ValueError, TypeError):
             acceptance_criteria = f"Target {target} {unit} (Tol: Check Drawing)"
    else:
        # Fallback for missing tolerances
        acceptance_criteria = f"Target {target} {unit} (Tolerance Not Defined)"

    # ... (rest of the function) ...
```

------

### Step 2: Create Data Seeding Script (`src/seed_history_data.py`)

**Objective**: Inject synthetic "Historical Defect Data" into Neo4j so the Graph RAG module has data to retrieve.

**Instructions for Cursor**:

- Create a new file: `src/seed_history_data.py`.
- Copy the following code into it. This script creates `DefectRecord` nodes linked to `ProcessStep` nodes (specifically targeting Step 20 and Step 80 to demonstrate the "Intelligent" features).

**File Content (`src/seed_history_data.py`)**:

```python
import random
from datetime import datetime, timedelta
from neo4j import GraphDatabase
from src.config import load_settings

def seed_defect_history():
    settings = load_settings()
    if not settings.neo4j.uri:
        print("Error: Neo4j URI not configured.")
        return

    driver = GraphDatabase.driver(
        settings.neo4j.uri, 
        auth=(settings.neo4j.username, settings.neo4j.password)
    )

    print("🌱 Seeding simulated historical defect data for Graph RAG...")

    queries = [
        # 1. Ensure Constraints
        "CREATE CONSTRAINT IF NOT EXISTS FOR (d:DefectRecord) REQUIRE d.id IS UNIQUE",
        
        # 2. Seed Defect for Step 20 (NC Routing)
        # Scenario: Tool wear causing undersize holes (High Risk)
        """
        MATCH (p:ProcessStep {step_id: '20'})
        WITH p
        UNWIND range(1, 5) as i
        MERGE (d:DefectRecord {id: 'DEF_NC_' + toString(i)})
        SET d.type = 'SizeDeviation',
            d.feature_size = 6.2,
            d.severity = 0.85,
            d.description = 'Hole diameter undersize due to cutter wear',
            d.occurred_at = toString(datetime() - duration({days: i*10}))
        MERGE (p)-[:HAS_DEFECT_HISTORY]->(d)
        """,

        # 3. Seed Defect for Step 80 (Forming)
        # Scenario: Springback issues (Medium Risk)
        """
        MATCH (p:ProcessStep {step_id: '80'})
        WITH p
        UNWIND range(1, 3) as i
        MERGE (d:DefectRecord {id: 'DEF_FORM_' + toString(i)})
        SET d.type = 'Springback',
            d.feature_size = 90.0,
            d.severity = 0.6,
            d.description = 'Angle springback exceeds tolerance',
            d.occurred_at = toString(datetime() - duration({days: i*15}))
        MERGE (p)-[:HAS_DEFECT_HISTORY]->(d)
        """
    ]

    with driver.session() as session:
        for q in queries:
            try:
                session.run(q)
            except Exception as e:
                print(f"Query failed: {e}")

    print("✅ History data seeded! 'Risk Miner' will now be active.")
    driver.close()

if __name__ == "__main__":
    seed_defect_history()
```

------

### Step 3: Execution & Verification

**Instructions for Cursor (Terminal)**:

1. Run the seeding script once:

   ```
   python -m src.seed_history_data
   ```

2. Run the inspection plan generator again (using the correct Part ID):

   ```
   python -m src.main_agent inspection-plan --part-id "C2 E53234023"
   ```

**Expected Result**:

- No crashes.
- Features without tolerances show "Tolerance Not Defined".
- **Intelligence Check**: The output for the **6.2mm Hole** should now indicate "High Risk" or recommend tighter inspection (CMM/100%) due to the injected "cutter wear" history.