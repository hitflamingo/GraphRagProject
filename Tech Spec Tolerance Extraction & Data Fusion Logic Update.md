# Tech Spec: Tolerance Extraction & Data Fusion Logic Update

## 1. Context & Problem Statement

We are building a pipeline to extract feature specifications from Engineering Drawings (PDF) and Process Cards (Excel) into Neo4j.

**The Problem**: The current VLM prompt for drawings incorrectly assumes all tolerances are explicitly marked (e.g., `±0.1`). However, real production drawings often rely on:

1. **General Tolerance Standards** referenced in the Title Block (e.g., "LIMITS NOT STATED ABD0001-1").
2. **Process Card Overrides**: The accompanying Excel file explicitly lists tolerances that are missing from the drawing (e.g., `Ф6.2±0.1mm`).

**The Goal**: Update the VLM Prompt and Python backend to handle "Implicit Tolerances" by extracting standard references and fusing data from the Process Card. **Do not allow the VLM to hallucinate default values.**

------

## 2. Action Items

### Task 1: Update VLM System Prompt (Drawing Parser)

**File**: (Locate your VLM processing script, e.g., `vlm_extractor.py`)

**Instruction**: Modify the `SYSTEM_PROMPT`.

1. **Remove** the instruction: "If tolerance not shown, use default: upper=+0.1, lower=-0.1". This is dangerous.
2. **Add** instruction to extract the "General Tolerance Standard" from the Title Block.
3. **Update** the JSON schema to include an `is_explicit` boolean flag and a `general_standard_ref` field.

**New System Prompt Template**:

```python
SYSTEM_PROMPT = """You are a senior QA Engineer specializing in technical drawing interpretation.

Task: Extract geometric features, explicit tolerances, and referenced standards.

Input Analysis Rules:
1. **Explicit Tolerances**: Only extract tolerances if they are visually written next to the dimension (e.g., "10 ±0.1" or GD&T frames).
2. **Implicit Tolerances**: If a dimension has NO tolerance marked, set "is_explicit": false and "tolerance": null. DO NOT GUESS OR INVENT DEFAULTS.
3. **General Standards**: Look at the Title Block for text like "LIMITS NOT STATED" or "GENERAL TOLERANCES". Extract the standard code (e.g., "ABD0001-1").

Return JSON format:
{
  "part_no": "string",
  "general_tolerance_standard": "stringOrNull", // Extracted from title block, e.g., "ABD0001-1"
  "features": [
    {
      "feature_id": "string",
      "type": "string",
      "target_value": float,
      "unit": "mm",
      "tolerance": {
         "is_explicit": boolean,  // true if written on drawing, false otherwise
         "upper": floatOrNull,
         "lower": floatOrNull,
         "type": "string"         // "symmetric", "limits", "gdt", or null
      },
      "bbox": [x1, y1, x2, y2]
    }
  ]
}
"""
```

### Task 2: Implement "Process Card" Tolerance Parser

**File**: (Locate your Excel parsing script, e.g., `process_card_parser.py`)

**Instruction**: The Excel file contains a specific column "说明 Note" (in the Sketch sheet) that lists the actual tolerances for the features.

1. Parse the `Note` column from the Excel file.
2. Use Regex or a lightweight LLM call to parse the string `Ф6.2±0.1mm、H=21.5±0.8mm` into a structured dictionary.

**Target Data Structure**:

```json
[
  {"feature_type": "Hole", "nominal": 6.2, "tol_plus": 0.1, "tol_minus": 0.1},
  {"feature_type": "Height", "nominal": 21.5, "tol_plus": 0.8, "tol_minus": 0.8}
]
```

### Task 3: Implement Data Fusion Logic (Backend)

**File**: (Locate your main logic or Neo4j ingestion script)

**Instruction**: When creating `Feature` nodes in Neo4j, apply the following **Priority Logic**:

1. **Priority 1 (Highest)**: **Process Card Data**. If the Excel parser found a tolerance for this feature (matching by nominal size/type), use it.
2. **Priority 2**: **Explicit Drawing Data**. If `is_explicit` is true from the VLM, use the VLM's output.
3. **Priority 3**: **General Standard**. If neither above exists, check `general_tolerance_standard`.
   - *Code Action*: If `general_tolerance_standard` is present (e.g., "ABD0001-1"), set a flag on the node `requires_standard_lookup: true`. (We will implement the standard lookup table in the next sprint).
4. **Priority 4**: **Alert**. If all fail, log a warning: "Missing Tolerance Information".

------

## 3. Reference Data (For Verification)

- **Evidence of General Standard**: In `xizi_part_1.png` title block: "LIMITS NOT STATED ABD0001-1".
- **Evidence of Process Tolerances**: In `xizi_card_1.xlsx` (Sketch Sheet): "Note: Ф6.2±0.1mm... R=4+1.5mm".