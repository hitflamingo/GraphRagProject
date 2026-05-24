# Implement Graph-Chain-of-Thought & Neuro-Symbolic Firewall

## 1. Context & Objective

We are upgrading an existing industrial Agentic AI system. The current implementation uses static vector retrieval (`risk_miner.py`) and unconstrained LLM planning (`cognitive_planner.py`).

**Goal:** Implement "Innovation Pillar 2" from our research paper:

1. **Graph-Chain-of-Thought (Graph-CoT):** Replace static retrieval with a dynamic, LLM-guided heuristic beam search over the Knowledge Graph.
2. **Neuro-Symbolic Firewall:** Implement a logic validation layer using SHACL-like rules to prevent LLM hallucinations in inspection plans.

**Existing Files (Context):**

- `src/risk_miner.py` (To be modified)
- `src/cognitive_planner.py` (To be modified)
- `src/config.py` (For settings)

------

## 2. Implementation Steps

### Step 1: Create the Reasoning Module (`src/reasoning/`)

Create a new directory `src/reasoning/` and implement the following files:

#### 1.1 `src/reasoning/graph_cot.py`

Create a class `GraphCoTReasoner`.

- **Dependencies:** `neo4j.Driver`, `openai.OpenAI`, `pydantic`.
- **Data Models:**
  - `ReasoningStep(BaseModel)`: `node_id`, `node_name`, `relation`, `score`, `reasoning`.
  - `GraphPath(BaseModel)`: `steps: List[ReasoningStep]`, `total_score: float`.
- **Core Method:** `perform_reasoning(start_node_uid, problem_context, max_depth=3, beam_width=3) -> List[GraphPath]`
- **Algorithm (Heuristic Beam Search):**
  1. Initialize paths with the anchor node.
  2. Loop `depth` from 0 to `max_depth`:
     - For each active path, query **all outgoing neighbors** using Cypher (match `(n)-[r]->(m)`).
     - **Batch Score:** Send `(current_node, relation, neighbor)` tuples to the LLM. Ask it to score relevance (0.0-1.0) to `problem_context`.
     - **Prune:** Keep only the top `beam_width` paths based on cumulative score.
  3. Return the top paths converted to text traces (e.g., "Feature -> Process -> Machine").

#### 1.2 `src/reasoning/constraints.json`

Create a JSON configuration file defining physical rules.

- **Schema:** List of objects with `id`, `description`, `type` ("static" or "topology"), and `logic`.
- **Examples:**
  - `CONST_01`: "Roughness Ra cannot be negative" (Static Python eval: `value >= 0`).
  - `CONST_02`: "Plastic material cannot undergo Heat Treatment" (Topology Cypher check).

#### 1.3 `src/reasoning/firewall.py`

Create a class `NeuroSymbolicFirewall`.

- **Dependencies:** `neo4j.Driver`.
- **Init:** Load `constraints.json`.
- **Core Method:** `validate_plan(part_id: str, plan: Dict) -> Tuple[bool, str]`
- **Logic:**
  1. Iterate through rules.
  2. If `type == "static"`, use `eval()` to check numeric fields in `plan`.
  3. If `type == "topology"`, execute a Cypher query to check graph consistency (e.g., check if `Part` linked to `Material` is compatible with `Process` implied by `plan`).
  4. Return `False` and an error message if any rule is violated.

------

### Step 2: Integrate Graph-CoT into `risk_miner.py`

Modify `src/risk_miner.py` to replace the static 1-hop search.

1. **Import:** `from src.reasoning.graph_cot import GraphCoTReasoner`.
2. **Init:** Initialize `self.reasoner` in `__init__`.
3. **Modify `assess_feature_risk`:**
   - Keep the vector search to find the **Anchor Node** (the `GeoFeature`).
   - **DELETE** the static `OPTIONAL MATCH` Cypher query for history.
   - **ADD** call to `self.reasoner.perform_reasoning(...)`.
     - `start_node_uid`: The UUID of the retrieved vector match.
     - `problem_context`: f"Feature {feature_id} type {type} target {target}".
   - **Output:** Convert the resulting `GraphPath` objects into string descriptions and append them to `risk_context["evidence"]`.

------

### Step 3: Integrate Firewall into `cognitive_planner.py`

Modify `src/cognitive_planner.py` to implement the "Generate-Validate-Repair" loop.

1. **Import:** `from src.reasoning.firewall import NeuroSymbolicFirewall`.
2. **Init:** Initialize `self.firewall` in `__init__` (requires passing `driver`).
3. **Modify `plan_inspection`:**
   - Wrap the LLM generation in a loop (e.g., `for attempt in range(3):`).
   - **Generate:** Call LLM to get JSON plan.
   - **Validate:** Call `self.firewall.validate_plan(part_id, plan)`.
   - **Success:** If valid, return `plan`.
   - **Repair:** If invalid, append the `feedback` string to the prompt: *"System Alert: Your plan violates physical constraints: {feedback}. Revise immediately."* and continue loop.
   - **Fallback:** If loop finishes without success, return a safe fallback plan with reasoning "Rejected by Firewall".

------

## 3. Technical Constraints

- **Type Hinting:** Strictly use `typing` module (`List`, `Dict`, `Optional`, `Any`).
- **Error Handling:** All Neo4j and OpenAI calls must be wrapped in `try-except` blocks.
- **Imports:** Fix all relative imports to work from the project root.
- **Pydantic:** Use Pydantic v2 if available, otherwise v1.

## 4. Execution Instruction

Please implement the **New Modules** first, then perform the **Integrations**. Do not delete existing logic in `config.py` or `tools.py`.