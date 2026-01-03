# Technical Spec: Process Card Data Fusion & Knowledge Graph Construction

## 1. Context & Objective

We are building a manufacturing quality knowledge graph. We need to fuse data from two sources:

1. **Visual Data (VLM)**: Geometric features (Holes, Edges) extracted from drawings.
2. **Process Data (Excel)**:
   - **Sheet 1 ("首页及工序页")**: Contains the manufacturing sequence (Process Steps).
   - **Sheet 2 ("草图页")**: Contains specific tolerance rules in the "Note" column (e.g., `Ф6.2±0.1mm`).

**Goal**: Parse the Excel file to extract steps and tolerance rules, then link these to the geometric features in Neo4j based on logical mapping (Heuristics) and numerical matching.

------

## 2. Implementation Roadmap

### Module A: Excel Parser Implementation (`src/parse_process_card.py`)

**Requirement**: Create a robust parser that handles multi-sheet logic and dynamic headers.

#### Task A.1: Parse Sheet 1 (Process Steps)

- **Target Sheet**: `首页及工序页` (or Index 0)

- **Logic**:

  1. Load sheet. Find the header row containing "工序" (Step) and "内容" (Description).
  2. Extract rows where `StepID` is valid.
  3. **Keyword Extraction**: For each step, identify its "Capability".
     - If description contains "铣" (Milling) or "NC"  -> Tag as `["Machining", "Hole_Making", "Profile_Cutting"]`.
     - If description contains "成形" (Forming) or "Hydraulic"  -> Tag as `["Bending", "Forming"]`.

- **Output Structure**:

  ```json
  [
    {"step_id": "20", "name": "NC Routing", "tags": ["Hole", "Edge"]},
    {"step_id": "80", "name": "Hydraulic Forming", "tags": ["Bend", "Surface"]}
  ]
  ```

#### Task A.2: Parse Sheet 2 (Tolerance Rules)

- **Target Sheet**: `草图页` (or Index containing "草图" or "Sketch")

- **Target Column**: "说明" or "Note".

- **Input String**: `Ф6.2±0.1mm、Ф3.2±0.1mm、H=8±0.8mm...`

- **Logic**: Use Regex to parse this string into a lookup dictionary.

- **Regex Pattern**: Match `(FeatureIdentifier)(NominalValue)(Tolerance)`.

  - *Example Matches*: `Ф6.2` -> `Hole`, `6.2`; `H=21.5` -> `Height`, `21.5`.

- **Output Structure**:

  ```json
  {
    "6.2": {"type": "Hole", "upper": 0.1, "lower": 0.1},
    "21.5": {"type": "Linear", "upper": 0.8, "lower": 0.8}
  }
  ```

------

### Module B: Graph Construction Logic (`src/graph_builder.py`)

**Requirement**: Update the Neo4j ingestion script to apply "Data Fusion" before creating nodes.

#### Logic B.1: Data Fusion (The "Glue")

Before creating `Feature` nodes, iterate through the VLM-extracted features:

1. Check the feature's `target_value` (e.g., 6.2).
2. Look up this value in the **Tolerance Output** (from Task A.2).
3. If a match is found, override the VLM's null tolerance with the Excel tolerance.

#### Logic B.2: Process Step Linking (The Relations)

When creating `Feature` nodes, link them to `ProcessStep` nodes based on the tags from Task A.1.

- **Mapping Rules**:

  - If Feature Type is **Hole** (Circle) or **Edge** (Profile) -> Link to Step **20 (NC Routing)**.
  - If Feature Type is **Bend** (Radius/Angle) -> Link to Step **80 (Hydraulic Forming)**.

- **Cypher Strategy**:

  ```cypher
  // 1. Create Process Steps
  MERGE (p:ProcessStep {step_id: "20"}) SET p.name = "NC Routing"
  MERGE (q:ProcessStep {step_id: "80"}) SET q.name = "Hydraulic Forming"
  
  // 2. Create Feature & Link (Dynamic Cypher)
  // For a Hole Feature:
  MATCH (s:ProcessStep {step_id: "20"})
  MERGE (f:Feature {id: "Hole_6.2"})
  MERGE (f)-[:PRODUCED_BY]->(s)
  ```

------

## 3. Cursor Instructions (Prompt)

**Copy and paste this into Cursor to generate the code:**

> **System**: You are an expert Python engineer with Pandas and Neo4j experience.
>
> **Task**: Implement the `ProcessCardParser` class and update `GraphBuilder` logic.
>
> **Step 1: Parsing Logic (`src/parse_process_card.py`)**
>
> - Create a function `extract_tolerance_rules(excel_path)`:
>   - Read the sheet named "草图页".
>   - Locate the cell under column "说明" (Note). content example: `Ф6.2±0.1mm...`.
>   - Parse this string into a dictionary: `{ "6.2": {"tol": 0.1}, ... }`.
> - Update `parse_excel_process_card(excel_path)`:
>   - Read "首页及工序页".
>   - Extract steps. Add a `capabilities` list to each step based on keywords:
>     - "铣" or "Routing" -> `["Hole", "Edge"]`
>     - "液压" or "Forming" -> `["Bend", "Angle"]`
>
> **Step 2: Graph Ingestion Logic (`src/main_agent.py` / `src/graph_builder.py`)**
>
> - Load `tolerance_rules` from Step 1.
> - Load `process_steps` from Step 1.
> - When iterating over Drawing Features (from VLM):
>   - **Fusion**: If `feature.value` exists in `tolerance_rules`, inject the tolerance.
>   - **Linking**:
>     - If `feature.type` is "Hole/Edge", add relationship `(Feature)-[:PRODUCED_BY]->(Step {id: "20"})`.
>     - If `feature.type` is "Bend", add relationship `(Feature)-[:PRODUCED_BY]->(Step {id: "80"})`.
>
> **Constraint**: Handle dynamic headers in Excel (do not assume row 0). Use the file `xizi_card_1.xlsx` as the reference schema.

------

## 4. Expected Graph Structure (Result)

After execution, the Neo4j graph should look like this:

*(Visual representation for your understanding)*

- **Node (Feature)**: `Hole_Φ6.2`
  - *Property*: `tolerance: ±0.1` (Sourced from Excel Sheet 2)
- **Node (ProcessStep)**: `Step_20` (NC Routing)
- **Relationship**: `(Hole_Φ6.2) -[:PRODUCED_BY]-> (Step_20)` (Inferred from Sheet 1 Keywords)