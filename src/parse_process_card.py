"""
Parse Excel process cards to extract structured process steps and parameters.
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from openai import OpenAI

from .config import Settings, build_openai_client, load_settings


LLM_EXTRACTION_PROMPT = """You are an expert in manufacturing process parameter extraction.
Extract all process parameters from the provided text description.

Look for:
1. Temperature values with tolerances (e.g., "(495±5)℃")
2. Time values with tolerances (e.g., "(35±5)min")
3. Pressure, speed, distance, or other numeric parameters
4. Referenced standards and documents (e.g., "AIPS03-11-001", "XA-OI-0310-01")
5. Machine/equipment names

Return ONLY a JSON object with this structure:
{
  "parameters": [
    {"name": "Temperature", "target_value": 495, "tolerance": 5, "unit": "C"},
    {"name": "Soaking Time", "target_value": 35, "tolerance": 5, "unit": "min"}
  ],
  "standards": ["XA-OI-0401", "AIPI04-01-001"],
  "equipment": ["NC Routing Machine"],
  "program_number": "0020"
}

If no parameters found, return empty lists. Always return valid JSON.
"""

TOLERANCE_EXTRACTION_PROMPT = """You are an expert in parsing dimensional tolerances from manufacturing notes.

Extract feature tolerances from the note text. Common formats:
- "Φ6.2±0.1mm" → Hole diameter 6.2mm with ±0.1mm tolerance
- "H=21.5±0.8mm" → Height 21.5mm with ±0.8mm tolerance  
- "R=4+1.5mm" → Radius 4mm with +1.5mm/-0mm tolerance (asymmetric)
- "L=50+0.2/-0.1mm" → Length 50mm with +0.2/-0.1mm tolerance

Return ONLY a JSON array:
[
  {
    "feature_type": "Hole|Height|Radius|Length|Width|Depth|Angle",
    "nominal": float,
    "tol_plus": float,
    "tol_minus": float,
    "unit": "mm|deg"
  }
]

If no tolerances found, return [].
"""


def extract_parameters_with_llm(
    description: str, client: OpenAI, model: str = "qwen-max"
) -> Dict[str, Any]:
    """
    Use LLM to extract process parameters from natural language descriptions.
    """
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": LLM_EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": f"Extract parameters from this process description:\n\n{description}",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"Warning: LLM extraction failed: {e}")
        return {"parameters": [], "standards": [], "equipment": [], "program_number": None}


def extract_tolerances_from_note(
    note_text: str, client: Optional[OpenAI] = None, model: str = "qwen-max"
) -> List[Dict[str, Any]]:
    """
    Extract feature tolerances from note text (e.g., "Φ6.2±0.1mm、H=21.5±0.8mm").
    
    Returns list of tolerance specifications.
    """
    if not note_text or pd.isna(note_text):
        return []
    
    note_text = str(note_text)
    
    # Try LLM extraction first if client available
    if client:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": TOLERANCE_EXTRACTION_PROMPT},
                    {"role": "user", "content": f"Extract tolerances from: {note_text}"}
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Handle both array and object responses
            if isinstance(result, list):
                return result
            elif isinstance(result, dict) and "tolerances" in result:
                return result["tolerances"]
            elif isinstance(result, dict) and len(result) > 0:
                # Might be wrapped in another key
                for key in result:
                    if isinstance(result[key], list):
                        return result[key]
            return []
        except Exception as e:
            print(f"Warning: LLM tolerance extraction failed: {e}")
    
    # Fallback to regex extraction
    return extract_tolerances_with_regex(note_text)


def _infer_step_capabilities(description: str, process_name: str) -> List[str]:
    """
    Infer process step capabilities based on keywords in description and name.
    
    Mapping rules from Technical Spec:
    - "铣" (Milling) or "NC" or "Routing" -> ["Machining", "Hole_Making", "Profile_Cutting"]
    - "成形" (Forming) or "液压" (Hydraulic) -> ["Bending", "Forming"]
    - Other keywords for additional capabilities
    
    Returns:
        List of capability tags (e.g., ["Hole", "Edge"] or ["Bend", "Angle"])
    """
    capabilities = []
    combined_text = (description + " " + process_name).lower()
    
    # Machining/Milling processes (creates holes and edges)
    if any(kw in combined_text for kw in ["铣", "nc", "routing", "milling", "切削", "drilling"]):
        capabilities.extend(["Machining", "Hole_Making", "Profile_Cutting"])
        # Add simple tags for linking
        capabilities.extend(["Hole", "Edge"])
    
    # Forming/Bending processes
    if any(kw in combined_text for kw in ["成形", "液压", "hydraulic", "forming", "bend", "弯曲"]):
        capabilities.extend(["Bending", "Forming"])
        # Add simple tags for linking
        capabilities.extend(["Bend", "Angle"])
    
    # Deburring/Finishing
    if any(kw in combined_text for kw in ["去毛刺", "deburr", "finishing", "polish"]):
        capabilities.append("Finishing")
    
    # Heat treatment
    if any(kw in combined_text for kw in ["热处理", "solution", "aging", "时效", "固溶"]):
        capabilities.append("HeatTreatment")
    
    # Surface treatment
    if any(kw in combined_text for kw in ["表面", "anodiz", "paint", "喷涂", "阳极"]):
        capabilities.append("SurfaceTreatment")
    
    # Inspection
    if any(kw in combined_text for kw in ["检验", "inspect", "quality"]):
        capabilities.append("Inspection")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_capabilities = []
    for cap in capabilities:
        if cap not in seen:
            seen.add(cap)
            unique_capabilities.append(cap)
    
    return unique_capabilities


def extract_tolerances_with_regex(note_text: str) -> List[Dict[str, Any]]:
    """
    Regex-based tolerance extraction from note text.
    
    Patterns:
    - Φ6.2±0.1mm → Hole diameter
    - H=21.5±0.8mm → Height
    - R=4+1.5mm → Radius (asymmetric)
    - L=50+0.2/-0.1mm → Length (asymmetric)
    """
    tolerances = []
    
    # Pattern 1: Φ6.2±0.1mm (symmetric tolerance)
    pattern_hole_sym = r'Φ\s*(\d+(?:\.\d+)?)\s*±\s*(\d+(?:\.\d+)?)\s*mm'
    for match in re.finditer(pattern_hole_sym, note_text):
        tolerances.append({
            "feature_type": "Hole",
            "nominal": float(match.group(1)),
            "tol_plus": float(match.group(2)),
            "tol_minus": float(match.group(2)),
            "unit": "mm"
        })
    
    # Pattern 2: H=21.5±0.8mm (Height, symmetric)
    pattern_height_sym = r'H\s*=\s*(\d+(?:\.\d+)?)\s*±\s*(\d+(?:\.\d+)?)\s*mm'
    for match in re.finditer(pattern_height_sym, note_text):
        tolerances.append({
            "feature_type": "Height",
            "nominal": float(match.group(1)),
            "tol_plus": float(match.group(2)),
            "tol_minus": float(match.group(2)),
            "unit": "mm"
        })
    
    # Pattern 3: R=4+1.5mm (Radius, asymmetric plus only)
    pattern_radius_plus = r'R\s*=\s*(\d+(?:\.\d+)?)\s*\+\s*(\d+(?:\.\d+)?)\s*mm'
    for match in re.finditer(pattern_radius_plus, note_text):
        tolerances.append({
            "feature_type": "Radius",
            "nominal": float(match.group(1)),
            "tol_plus": float(match.group(2)),
            "tol_minus": 0.0,
            "unit": "mm"
        })
    
    # Pattern 4: L=50+0.2/-0.1mm (Length, asymmetric)
    pattern_asym = r'([LWHD])\s*=\s*(\d+(?:\.\d+)?)\s*\+\s*(\d+(?:\.\d+)?)\s*/\s*-\s*(\d+(?:\.\d+)?)\s*mm'
    type_map = {"L": "Length", "W": "Width", "H": "Height", "D": "Depth"}
    for match in re.finditer(pattern_asym, note_text):
        tolerances.append({
            "feature_type": type_map.get(match.group(1), "Dimension"),
            "nominal": float(match.group(2)),
            "tol_plus": float(match.group(3)),
            "tol_minus": float(match.group(4)),
            "unit": "mm"
        })
    
    return tolerances


def extract_step_capabilities(step_name: str, description: str) -> List[str]:
    """
    Extract capability tags for a process step based on keywords.
    
    According to Tech Spec Task A.1:
    - "铣" (Milling) or "NC" or "Routing" -> ["Machining", "Hole_Making", "Profile_Cutting", "Hole", "Edge"]
    - "成形" (Forming) or "液压" (Hydraulic) -> ["Bending", "Forming", "Bend", "Angle"]
    
    Args:
        step_name: Process step name
        description: Process step description
        
    Returns:
        List of capability tags (e.g., ["Hole", "Edge"] or ["Bend", "Angle"])
    """
    tags = []
    combined_text = f"{step_name} {description}".lower()
    
    # Machining operations (Holes, Edges, Profiles) - Task A.1
    if any(keyword in combined_text for keyword in ["铣", "nc", "routing", "milling", "切削"]):
        tags.extend(["Machining", "Hole_Making", "Profile_Cutting", "Hole", "Edge"])
    
    # Forming operations (Bends, Angles) - Task A.1
    if any(keyword in combined_text for keyword in ["成形", "液压", "hydraulic", "forming", "弯曲"]):
        tags.extend(["Bending", "Forming", "Bend", "Angle"])
    
    # Additional process types
    if any(keyword in combined_text for keyword in ["去毛刺", "deburr", "benchwork"]):
        tags.append("Finishing")
    
    if any(keyword in combined_text for keyword in ["清洗", "clean"]):
        tags.append("Cleaning")
    
    if any(keyword in combined_text for keyword in ["热处理", "solution", "固溶", "时效", "aging"]):
        tags.append("Heat_Treatment")
    
    if any(keyword in combined_text for keyword in ["阳极", "anodiz", "tsa"]):
        tags.extend(["Surface_Treatment", "Anodizing"])
    
    if any(keyword in combined_text for keyword in ["喷漆", "涂装", "paint", "primer", "topcoat"]):
        tags.extend(["Surface_Treatment", "Painting"])
    
    if any(keyword in combined_text for keyword in ["检验", "检查", "inspect"]):
        tags.append("Inspection")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_tags = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)
    
    return unique_tags


def extract_parameters_with_regex(description: str) -> Dict[str, Any]:
    """
    Fallback regex-based parameter extraction (less accurate than LLM).
    """
    parameters = []
    standards = []
    
    # Extract temperature: (495±5)℃ or 495±5℃
    temp_pattern = r'\((\d+(?:\.\d+)?)\s*±\s*(\d+(?:\.\d+)?)\)\s*℃'
    for match in re.finditer(temp_pattern, description):
        parameters.append({
            "name": "Temperature",
            "target_value": float(match.group(1)),
            "tolerance": float(match.group(2)),
            "unit": "C"
        })
    
    # Extract time: (35±5)min
    time_pattern = r'\((\d+(?:\.\d+)?)\s*±\s*(\d+(?:\.\d+)?)\)\s*min'
    for match in re.finditer(time_pattern, description):
        parameters.append({
            "name": "Time",
            "target_value": float(match.group(1)),
            "tolerance": float(match.group(2)),
            "unit": "min"
        })
    
    # Extract temperature range: 15℃～32℃
    range_pattern = r'(\d+(?:\.\d+)?)\s*℃\s*[～~]\s*(\d+(?:\.\d+)?)\s*℃'
    for match in re.finditer(range_pattern, description):
        parameters.append({
            "name": "Temperature Range",
            "min_value": float(match.group(1)),
            "max_value": float(match.group(2)),
            "unit": "C"
        })
    
    # Extract standards: AIPS03-11-001, XA-OI-0310-01, etc.
    standard_pattern = r'\b([A-Z]{2,}[\-\d]+(?:[-/][A-Z0-9]+)*)\b'
    standards = list(set(re.findall(standard_pattern, description)))
    
    return {
        "parameters": parameters,
        "standards": standards,
        "equipment": [],
        "program_number": None
    }


def extract_tolerance_rules_from_sketch(
    excel_path: str,
    settings: Optional[Settings] = None,
    use_llm: bool = True
) -> Dict[str, Dict[str, Any]]:
    """
    Extract tolerance rules from sketch sheet and return as a lookup dictionary.
    
    According to Tech Spec Task A.2:
    - Target Sheet: "草图页" (Sketch)
    - Target Column: "说明" (Note)
    - Input Example: "Ф6.2±0.1mm、Ф3.2±0.1mm、H=8±0.8mm..."
    - Output Format: { "6.2": {"type": "Hole", "upper": 0.1, "lower": 0.1}, ... }
    
    Args:
        excel_path: Path to Excel file
        settings: Application settings
        use_llm: Whether to use LLM for tolerance extraction
        
    Returns:
        Dictionary mapping target_value (as string) to tolerance info
    """
    settings = settings or load_settings()
    file_path = Path(excel_path)
    
    tolerance_dict = {}
    
    try:
        # Read sketch sheet
        excel_file = pd.ExcelFile(file_path)
        sketch_df = None
        for sheet_name in excel_file.sheet_names:
            if 'sketch' in sheet_name.lower() or '草图' in sheet_name:
                sketch_df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
                print(f"   Found sketch sheet: {sheet_name}")
                break
        
        if sketch_df is None:
            print("   Warning: No sketch sheet found in Excel file")
            return tolerance_dict
        
        # Initialize LLM client if requested
        client = None
        if use_llm and settings.openai.api_key:
            try:
                client = build_openai_client(settings)
            except Exception as e:
                print(f"   Warning: Could not initialize LLM client: {e}")
        
        # Primary strategy: find rows whose cells contain "说明"/"note" and parse the rest of that row as tolerance text
        tolerance_rows_found = False
        for _, row in sketch_df.iterrows():
            row_strs = [str(c) for c in row if isinstance(c, str)]
            lower_join = " ".join(row_strs).lower()
            if "说明" in lower_join or "note" in lower_join:
                tolerance_rows_found = True
                # Remove the header cells containing 说明/note; parse the remaining cells as tolerance text
                text_cells = [
                    s for s in row_strs
                    if "说明" not in s.lower() and "note" not in s.lower()
                ]
                if not text_cells:
                    continue
                note_text = "、".join(text_cells)
                tolerances = extract_tolerances_from_note(
                    note_text,
                    client if use_llm else None,
                    "qwen-max"
                )
                for tol in tolerances:
                    nominal_str = str(tol.get("nominal"))
                    upper_val, lower_val = tol.get("tol_plus"), tol.get("tol_minus")
                    tolerance_dict[nominal_str] = {
                        "type": tol.get("feature_type", "Unknown"),
                        "upper": upper_val,
                        "lower": lower_val,
                        "unit": tol.get("unit", "mm")
                    }
        
        # Fallback: if no tolerance rows detected, try old column-based approach
        if not tolerance_rows_found and not tolerance_dict:
            note_col = None
            for col in sketch_df.columns:
                col_str = str(col).lower()
                if 'note' in col_str or '说明' in col_str or '备注' in col_str:
                    note_col = col
                    break
            if note_col is not None:
                for _, row in sketch_df.iterrows():
                    note_text = row[note_col]
                    if not pd.isna(note_text):
                        tolerances = extract_tolerances_from_note(
                            str(note_text),
                            client if use_llm else None,
                            "qwen-max"
                        )
                        for tol in tolerances:
                            nominal_str = str(tol.get("nominal"))
                            upper_val, lower_val = tol.get("tol_plus"), tol.get("tol_minus")
                            tolerance_dict[nominal_str] = {
                                "type": tol.get("feature_type", "Unknown"),
                                "upper": upper_val,
                                "lower": lower_val,
                                "unit": tol.get("unit", "mm")
                            }
        
        print(f"   Extracted {len(tolerance_dict)} tolerance rules from sketch")
    
    except Exception as e:
        print(f"   Warning: Failed to extract tolerance rules from sketch: {e}")
        import traceback
        traceback.print_exc()
    
    return tolerance_dict


def parse_excel_process_card(
    excel_path: str,
    settings: Optional[Settings] = None,
    use_llm: bool = True,
    extract_tolerances: bool = True
) -> Dict[str, Any]:
    """
    Parse Excel process card and extract structured data including feature tolerances.
    
    Args:
        excel_path: Path to Excel file (or CSV)
        settings: Application settings
        use_llm: Whether to use LLM for parameter extraction
        extract_tolerances: Whether to extract feature tolerances from note columns
        
    Returns:
        Dictionary containing part_id, process_steps, feature_tolerances, and metadata
    """
    settings = settings or load_settings()
    file_path = Path(excel_path)
    
    def _find_process_header_row(df: pd.DataFrame) -> Optional[int]:
        """
        Find the row index that contains both '工序' (step) and '工作内容' (description).
        This handles files where the first ~30 rows are metadata.
        """
        for idx, row in df.iterrows():
            row_text = " ".join([str(c) for c in row if isinstance(c, str)]).lower()
            if "工序" in row_text and "工作内容" in row_text:
                return idx
        return None
    
    def _apply_header(df: pd.DataFrame, header_idx: int) -> pd.DataFrame:
        """Reassign headers using the detected header row and drop rows above it."""
        headers = []
        raw_headers = df.iloc[header_idx].tolist()
        for i, h in enumerate(raw_headers):
            if pd.isna(h):
                headers.append(f"col_{i}")
            else:
                headers.append(str(h).strip())
        df_clean = df.iloc[header_idx + 1 :].copy()
        df_clean.columns = headers
        df_clean = df_clean.reset_index(drop=True)
        return df_clean
    
    # Try to read as Excel or CSV
    try:
        if file_path.suffix.lower() == '.csv':
            df = pd.read_csv(file_path, header=None)
        else:
            # Try to read all sheets
            excel_file = pd.ExcelFile(file_path)
            df = pd.read_excel(file_path, header=None)
            
            # Check for "Sketch" or "草图" sheet for tolerances
            sketch_df = None
            for sheet_name in excel_file.sheet_names:
                if 'sketch' in sheet_name.lower() or '草图' in sheet_name:
                    sketch_df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
                    break
    except Exception as e:
        raise ValueError(f"Failed to read file {excel_path}: {e}")
    
    # Locate the real header row and reassign columns
    header_idx = _find_process_header_row(df)
    if header_idx is None:
        raise ValueError("Could not locate process header row (looking for '工序' and '工作内容').")
    df = _apply_header(df, header_idx)
    
    # Clean DataFrame - remove completely empty rows
    df = df.dropna(how='all')
    
    # Expected columns (adjust based on actual Excel structure)
    # Common patterns: 工序号/Step, 工序描述/Process, 工作内容/Description
    # NOTE: Fields may span multiple columns due to merged cells; collect and merge.
    step_cols: List[str] = []
    name_cols: List[str] = []
    desc_cols: List[str] = []
    
    for col in df.columns:
        col_str = str(col).lower()
        # Step number columns: contain 工序/step but NOT description/content keywords
        if (('工序' in col_str or 'step' in col_str)
            and not any(k in col_str for k in ['描述', 'description', '内容', 'process'])):
            step_cols.append(col)
            continue
        # Process name columns: 工序描述/工序名称/process/工艺/tooling/工装/版次
        if any(k in col_str for k in ['工序描述', '工序名称', 'process', '工艺', 'tooling', '工装', '版次']):
            name_cols.append(col)
            continue
        # Work content/description columns
        if any(k in col_str for k in ['工作内容', '描述', 'description', 'content']):
            desc_cols.append(col)
            continue
    
    # Fallback: be lenient if still empty
    if not step_cols:
        step_cols = [c for c in df.columns if '工序' in str(c).lower() or 'step' in str(c).lower()]
    if not name_cols:
        name_cols = [c for c in df.columns if any(k in str(c).lower() for k in ['process', '工艺', '工序'])]
    if not desc_cols:
        desc_cols = [c for c in df.columns if any(k in str(c).lower() for k in ['描述', 'description', '内容'])]
    
    if not step_cols or not name_cols or not desc_cols:
        raise ValueError(
            f"Could not identify required columns. Found columns: {list(df.columns)}"
        )
    
    def _merge_columns(row, cols: List[str]) -> Optional[str]:
        """Merge values from multiple columns, handling NaN and whitespace."""
        values = []
        for col in cols:
            val = row[col] if col in row else None
            if not pd.isna(val):
                val_str = str(val).strip()
                if val_str and val_str not in values:
                    values.append(val_str)
        return " ".join(values) if values else None
    
    # Create standardized merged columns
    df["StepID"] = df.apply(lambda row: _merge_columns(row, step_cols), axis=1)
    df["ProcessName"] = df.apply(lambda row: _merge_columns(row, name_cols), axis=1)
    df["Description"] = df.apply(lambda row: _merge_columns(row, desc_cols), axis=1)
    
    # Filter out rows without step id
    df = df[df["StepID"].notna()]
    
    # Initialize LLM client if requested (LLM model is text-only, qwen-max)
    client = None
    llm_model = "qwen-max"
    if use_llm and settings.openai.api_key:
        try:
            client = build_openai_client(settings)
        except Exception as e:
            print(f"Warning: Could not initialize LLM client: {e}")
    
    # Extract part_id from filename or first row
    part_id = file_path.stem
    
    process_steps = []
    for _, row in df.iterrows():
        step_number = row["StepID"]
        process_name = row["ProcessName"]
        description = row["Description"]
        
        # Skip if essential fields are missing
        if pd.isna(step_number) or pd.isna(process_name):
            continue
        
        description = str(description) if not pd.isna(description) else ""
        
        # Extract parameters
        if client and use_llm:
            extracted = extract_parameters_with_llm(description, client, llm_model)
        else:
            extracted = extract_parameters_with_regex(description)
        
        # Task A.1: Extract capability tags for linking to features
        capabilities = extract_step_capabilities(str(process_name), description)
        
        step_data = {
            "step_number": str(step_number).strip(),
            "step_id": str(step_number).strip(),  # Alias for compatibility
            "process_name": str(process_name).strip(),
            "name": str(process_name).strip(),  # Alias for compatibility
            "description": description,
            "parameters": extracted.get("parameters", []),
            "standards": extracted.get("standards", []),
            "equipment": extracted.get("equipment", []),
            "program_number": extracted.get("program_number"),
            "capabilities": capabilities,  # Task A.1: Capability tags
            "tags": capabilities  # Alias for graph linking (Task B.2)
        }
        
        process_steps.append(step_data)
    
    # Task A.2: Extract tolerance rules from Sketch sheet as lookup dictionary
    tolerance_rules = {}
    feature_tolerances = []  # Legacy format for backward compatibility
    
    if extract_tolerances:
        tolerance_rules = extract_tolerance_rules_from_sketch(
            excel_path, settings, use_llm
        )
        
        # Also keep the old list format for backward compatibility
        for nominal, rule in tolerance_rules.items():
            feature_tolerances.append({
                "feature_type": rule.get("type"),
                "nominal": float(nominal) if nominal.replace('.', '').replace('-', '').isdigit() else None,
                "tol_plus": rule.get("upper"),
                "tol_minus": rule.get("lower"),
                "unit": rule.get("unit", "mm")
            })
    
    return {
        "part_id": part_id,
        "process_steps": process_steps,
        "tolerance_rules": tolerance_rules,  # Task A.2: Lookup dictionary
        "feature_tolerances": feature_tolerances,  # Legacy format
        "total_steps": len(process_steps)
    }


def main():
    """Command-line interface for testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Parse Excel process card")
    parser.add_argument("--excel", required=True, help="Path to Excel/CSV file")
    parser.add_argument("--output", help="Output JSON path (optional)")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM extraction")
    
    args = parser.parse_args()
    
    result = parse_excel_process_card(args.excel, use_llm=not args.no_llm)
    
    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    
    if args.output:
        Path(args.output).write_text(output_json, encoding='utf-8')
        print(f"Output written to {args.output}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
