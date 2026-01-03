# Data Fusion Usage Guide

## Overview

This guide demonstrates the **Data Fusion** workflow implemented according to the Technical Specification for Process Card Data Fusion & Knowledge Graph Construction.

The system performs:
1. **Module A**: Parse drawing (VLM) and process card (Excel/LLM)
2. **Module B**: Apply data fusion (tolerance rules) and process step linking

---

## Quick Start

### Command Line Usage

```bash
# Run data fusion workflow with both drawing and process card
python -m src.main_agent ingest-fusion \
  --drawing data/xizi_part_1.png \
  --process-card data/xizi_card_1.xlsx \
  --output results/fusion_results.json
```

### What Happens

1. **Drawing Extraction** (VLM)
   - Extracts geometric features (Holes, Edges, Bends, etc.)
   - Some features may have `null` tolerances if not explicitly marked on drawing

2. **Process Card Parsing** (LLM)
   - **Sheet 1 ("首页及工序页")**: Extracts process steps with capability tags
     - Example: Step 20 "NC Routing" → Tags: `["Hole", "Edge", "Machining"]`
   - **Sheet 2 ("草图页")**: Extracts tolerance rules from "说明" column
     - Example: `Φ6.2±0.1mm` → `{"6.2": {"type": "Hole", "upper": 0.1, "lower": 0.1}}`

3. **Data Fusion** (Logic B.1)
   - Matches feature `target_value` to tolerance rules
   - Overrides VLM's `null` tolerance with Excel tolerance
   - Example: Feature `Hole_6.2mm` gets tolerance `±0.1mm` from process card

4. **Process Step Linking** (Logic B.2)
   - Links features to process steps based on type matching
   - Hole/Edge features → Linked to Step 20 (NC Routing)
   - Bend/Angle features → Linked to Step 80 (Hydraulic Forming)

---

## Technical Spec Implementation

### Task A.1: Process Step Capability Tagging

```python
# src/parse_process_card.py
def extract_step_capabilities(step_name: str, description: str) -> List[str]:
    """
    Extract capability tags based on keywords:
    - "铣"/"NC"/"Routing" → ["Machining", "Hole_Making", "Profile_Cutting", "Hole", "Edge"]
    - "成形"/"液压"/"Hydraulic" → ["Bending", "Forming", "Bend", "Angle"]
    """
```

**Output Example**:
```json
{
  "step_number": "20",
  "process_name": "NC Routing",
  "capabilities": ["Machining", "Hole_Making", "Profile_Cutting", "Hole", "Edge"]
}
```

### Task A.2: Tolerance Rules Extraction

```python
# src/parse_process_card.py
def extract_tolerance_rules_from_sketch(excel_path: str) -> Dict[str, Dict]:
    """
    Parse tolerance rules from sketch sheet.
    Input: "Φ6.2±0.1mm、H=21.5±0.8mm、R=4+1.5mm"
    Output: {"6.2": {"type": "Hole", "upper": 0.1, "lower": 0.1}, ...}
    """
```

**Output Example**:
```json
{
  "6.2": {"type": "Hole", "upper": 0.1, "lower": 0.1, "unit": "mm"},
  "21.5": {"type": "Height", "upper": 0.8, "lower": 0.8, "unit": "mm"}
}
```

### Logic B.1: Data Fusion

```python
# src/graph_builder.py
def build_fused_graph(self, extraction: Dict, process_data: Dict):
    """
    Apply tolerance rules from process card to VLM features.
    If feature.target_value matches a tolerance rule, override null tolerance.
    """
```

**Before Fusion**:
```json
{
  "feature_id": "Hole_01",
  "type": "HoleDiameter",
  "target_value": 6.2,
  "tolerance": {"is_explicit": false, "upper": null, "lower": null}
}
```

**After Fusion**:
```json
{
  "feature_id": "Hole_01",
  "type": "HoleDiameter",
  "target_value": 6.2,
  "tolerance": {
    "is_explicit": true,
    "upper": 0.1,
    "lower": -0.1,
    "type": "symmetric",
    "source": "process_card"
  }
}
```

### Logic B.2: Process Step Linking

```python
# src/graph_builder.py (in build_fused_graph)
# Mapping rules:
# - Hole/Edge features → Link to Machining steps (tags: ["Hole", "Edge"])
# - Bend/Angle features → Link to Forming steps (tags: ["Bend", "Angle"])
```

**Neo4j Relationships Created**:
```cypher
(f:GeoFeature {feature_id: "Hole_6.2"})-[:PRODUCED_BY]->(s:ProcessStep {step_id: "xizi_card_1_Step20"})
```

---

## Expected Graph Structure

After running the fusion workflow, the Neo4j graph contains:

```
Part: xizi_card_1
├── GeoFeature: Hole_6.2mm
│   ├── tolerance: ±0.1mm (from process card)
│   └── [PRODUCED_BY] → ProcessStep: Step_20 (NC Routing)
├── GeoFeature: Edge_50mm
│   └── [PRODUCED_BY] → ProcessStep: Step_20 (NC Routing)
├── GeoFeature: BendAngle_90deg
│   └── [PRODUCED_BY] → ProcessStep: Step_80 (Hydraulic Forming)
└── ProcessSteps:
    ├── Step_10 (Incoming Inspection)
    ├── Step_20 (NC Routing) ← Links to Holes/Edges
    ├── Step_80 (Hydraulic Forming) ← Links to Bends
    └── ...
```

---

## Verification

### Query Fused Tolerances

```cypher
// Find features with tolerances from process card
MATCH (f:GeoFeature)
WHERE f.tol_source = 'process_card' OR f.tolerance CONTAINS 'process_card'
RETURN f.feature_id, f.target_value, f.tol_upper, f.tol_lower
```

### Query Feature-Process Links

```cypher
// Find which features are produced by which steps
MATCH (f:GeoFeature)-[:PRODUCED_BY]->(s:ProcessStep)
RETURN f.feature_id, f.type, s.step_id, s.name
ORDER BY s.step_id
```

### Example Output

| feature_id | type | step_id | name |
|------------|------|---------|------|
| Hole_6.2 | HoleDiameter | xizi_card_1_Step20 | NC Routing |
| Edge_50 | EdgeLength | xizi_card_1_Step20 | NC Routing |
| Bend_90 | BendAngle | xizi_card_1_Step80 | Hydraulic Forming |

---

## Advanced Usage

### Python API

```python
from src.main_agent import MainAgent

agent = MainAgent()

# Run fusion workflow
result = agent.ingest_with_fusion(
    drawing_path="data/xizi_part_1.png",
    process_card_path="data/xizi_card_1.xlsx",
    use_llm=True,  # Use LLM for process card parsing
    advanced_mode=True  # Use multi-stage VLM extraction
)

# Access results
extraction = result["extraction"]
process_data = result["process_data"]
part_id = result["part_id"]

print(f"Features: {len(extraction['features'])}")
print(f"Process steps: {len(process_data['process_steps'])}")
print(f"Tolerance rules: {len(process_data['tolerance_rules'])}")

agent.close()
```

### Without LLM (Regex-based fallback)

```bash
python -m src.main_agent ingest-fusion \
  --drawing data/xizi_part_1.png \
  --process-card data/xizi_card_1.xlsx \
  --no-llm
```

---

## Troubleshooting

### Issue: "Could not locate process header row"

**Cause**: Excel file has unusual header structure.

**Solution**: The parser looks for rows containing "工序" AND "工作内容". Verify these keywords exist in your Excel file.

### Issue: "No tolerance rules extracted"

**Cause**: Sketch sheet not found or "说明" column missing.

**Solution**: Ensure your Excel has a sheet named "草图页" (or containing "sketch") with a "说明"/"Note" column.

### Issue: "No features linked to process steps"

**Cause**: Feature types don't match step capability tags.

**Solution**: Check if your features are recognized types (HoleDiameter, EdgeLength, BendAngle) and process steps have correct keywords ("铣", "液压", etc.).

---

## References

- Technical Spec: `Technical Spec Process Card Data Fusion & Knowledge Graph Construction.md`
- Implementation:
  - `src/parse_process_card.py`: Module A (Excel parsing)
  - `src/graph_builder.py`: Module B (Data fusion and linking)
  - `src/main_agent.py`: Workflow orchestration

