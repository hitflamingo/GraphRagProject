import base64
import json
from pathlib import Path
from typing import Any, Dict, Optional
import tempfile
import re

from openai import OpenAI

from .config import Settings, build_openai_client, load_settings

# Optional imports for PDF support
try:
    from pdf2image import convert_from_path
    from PIL import Image
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# Optional import for better JSON parsing
try:
    import json5
    JSON5_SUPPORT = True
except ImportError:
    JSON5_SUPPORT = False

SYSTEM_PROMPT = """You are a senior QA Engineer specializing in technical drawing interpretation.

Task: Extract geometric features, EXPLICIT tolerances ONLY, and referenced standards.

**CRITICAL RULES FOR TOLERANCE EXTRACTION**:
1. **Explicit Tolerances ONLY**: Extract tolerance values ONLY if they are visually written next to the dimension (e.g., "10±0.1", "6.2+0.1/-0.05", or GD&T frames with tolerance values).
2. **NO Default Values**: If a dimension has NO tolerance marked on the drawing, set "is_explicit": false and "upper": null, "lower": null. DO NOT GUESS, INVENT, OR USE DEFAULT VALUES.
3. **General Tolerance Standards**: Look at the Title Block for references like "LIMITS NOT STATED ABD0001-1" or "GENERAL TOLERANCES PER XXX". Extract the standard code.

Feature Types to Extract:
- EdgeLength, ArcRadius, HoleRadius, HoleDiameter, HoleToHoleDist, HoleToEdgeDist, BendAngle, BendRadius

Return JSON format:
{
  "part_id": "string",
  "part_number": "string (e.g., E53234023200-01)",
  "material": "string",
  "material_state": "string (e.g., 2024-O)",
  "general_tolerance_standard": "string or null",
  "features": [
    {
      "feature_id": "string (e.g., Hole_01, Edge_01)",
      "type": "string",
      "target_value": float,
      "unit": "mm",
      "tolerance": {
        "is_explicit": boolean,
        "upper": float or null,
        "lower": float or null,
        "type": "symmetric|limits|gdt|null"
      },
      "bbox": [x1, y1, x2, y2],
      "gdt": {
        "type": "Position|Perpendicularity|etc",
        "value": float,
        "datums": ["A", "B", "C"]
      }
    }
  ],
  "standards": ["string"],
  "notes": ["string"]
}

Examples:
- Dimension "Φ6.2±0.1" → is_explicit: true, upper: 0.1, lower: -0.1
- Dimension "Φ6.2" with no tolerance → is_explicit: false, upper: null, lower: null
- Title block "ABD0001-1" → general_tolerance_standard: "ABD0001-1"

Return ONLY valid JSON. No comments, no markdown wrappers.
Output pure minified JSON without markdown formatting to save tokens."""


HEADER_EXTRACTION_PROMPT = """Extract metadata from the drawing header/title block.
Look for:
- Part Number (零件号/Part No)
- Material specification (材料/Material)
- Material state (状态/State, e.g., 2024-O, W, T4)
- Drawing number
- Revision
- Scale
- Unfolded dimensions (展开尺寸)

Return JSON only:
{
  "part_number": "string",
  "material": "string",
  "material_state": "string",
  "scale": "string",
  "revision": "string",
  "unfolded_dimensions": {"length": float, "width": float, "unit": "mm"}
}"""


GDT_EXTRACTION_PROMPT = """Extract all GD&T (Geometric Dimensioning and Tolerancing) specifications.
Focus on:
- Position tolerances (⊕ symbol with Φ value)
- Datum references (A, B, C)
- Perpendicularity, parallelism, flatness specifications
- Surface finish requirements

Return JSON array:
{
  "gdt_callouts": [
    {
      "type": "Position",
      "value": 0.1,
      "datums": ["A", "B"],
      "applied_to": "Hole_01",
      "bbox": [x1, y1, x2, y2]
    }
  ]
}"""


def _clean_json_string(json_str: str) -> str:
    """
    Clean JSON string to remove common formatting issues.
    """
    import re
    
    # Remove C-style comments (// ...)
    json_str = re.sub(r'//[^\n]*', '', json_str)
    
    # Remove multi-line comments (/* ... */)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
    
    # Remove trailing commas before } or ]
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    return json_str


def _parse_json_robust(json_str: str) -> Dict[str, Any]:
    """
    Robustly parse JSON with multiple fallback strategies.
    """
    # Strategy 1: Standard JSON
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  Standard JSON parse failed: {e} (content length: {len(json_str)})")
    
    # Strategy 2: Clean and retry
    try:
        cleaned = _clean_json_string(json_str)
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"  Cleaned JSON parse failed: {e}")
    
    # Strategy 3: Use json5 (if available)
    if JSON5_SUPPORT:
        try:
            import json5
            return json5.loads(json_str)
        except Exception as e:
            print(f"  JSON5 parse failed: {e}")
    
    # Strategy 4: Try to fix truncated JSON
    try:
        # If JSON is truncated, try to close it
        truncated_fixed = _fix_truncated_json(json_str)
        if truncated_fixed:
            return json.loads(truncated_fixed)
    except Exception as e:
        print(f"  Truncation fix failed: {e}")
    
    # Strategy 5: Extract JSON from markdown code blocks
    try:
        # Sometimes VLM wraps JSON in ```json ... ```
        import re
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', json_str, re.DOTALL)
        if match:
            return json.loads(match.group(1))
    except Exception as e:
        print(f"  Markdown extraction failed: {e}")
    
    # Strategy 6: Try to find the largest valid JSON object
    try:
        import re
        # Find all potential JSON objects
        matches = list(re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', json_str))
        # Try from largest to smallest
        matches.sort(key=lambda m: len(m.group(0)), reverse=True)
        for match in matches:
            try:
                return json.loads(match.group(0))
            except:
                continue
    except Exception as e:
        print(f"  Partial extraction failed: {e}")
    
    # All strategies failed
    raise ValueError("Could not parse JSON with any strategy")


def _fix_truncated_json(json_str: str) -> Optional[str]:
    """
    Try to fix truncated JSON by closing unclosed brackets/braces.
    """
    # Count opening and closing brackets
    open_braces = json_str.count('{')
    close_braces = json_str.count('}')
    open_brackets = json_str.count('[')
    close_brackets = json_str.count(']')
    
    # If severely imbalanced, likely truncated
    if open_braces > close_braces or open_brackets > close_brackets:
        print(f"  Detected truncation: {open_braces} {{ vs {close_braces} }}, {open_brackets} [ vs {close_brackets} ]")
        
        # Try to close the JSON
        fixed = json_str.rstrip()
        
        # Remove trailing comma if exists
        if fixed.endswith(','):
            fixed = fixed[:-1]
        
        # Close arrays
        fixed += ']' * (open_brackets - close_brackets)
        
        # Close objects
        fixed += '}' * (open_braces - close_braces)
        
        return fixed
    
    return None


def _encode_image_to_base64(image_path: Path) -> str:
    """
    Encode image to base64. Supports PDF conversion.
    """
    # Check if it's a PDF
    if image_path.suffix.lower() == '.pdf':
        if not PDF_SUPPORT:
            raise ImportError(
                "PDF support requires pdf2image and Pillow. "
                "Install with: pip install pdf2image Pillow"
            )
        
        # Convert PDF to image (first page only)
        try:
            images = convert_from_path(str(image_path), first_page=1, last_page=1, dpi=200)
            if not images:
                raise ValueError(f"Could not convert PDF: {image_path}")
            
            # Save to temporary PNG file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)
                images[0].save(tmp_path, 'PNG')
            
            # Read the PNG and encode
            with tmp_path.open("rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
            
            # Clean up temp file
            tmp_path.unlink()
            
            return encoded
        except Exception as e:
            raise ValueError(f"Failed to convert PDF to image: {e}")
    
    # Regular image file
    with image_path.open("rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _mock_extraction(part_id: str) -> Dict[str, Any]:
    """Deterministic fallback when no API key is provided."""
    return {
        "part_id": part_id,
        "general_tolerance_standard": None,  # No general standard in mock
        "features": [
            {
                "feature_id": "Edge_01",
                "feature_uid": f"{part_id}::Edge_01",
                "type": "EdgeLength",
                "target_value": 50.0,
                "unit": "mm",
                "tolerance": {
                    "is_explicit": True,  # Mock data has explicit tolerances
                    "upper": 0.1,
                    "lower": -0.1,
                    "type": "symmetric"
                },
                "bbox": [100, 200, 300, 200],
                "related_process": {
                    "action_id": "Bend_01",
                    "name": "Bending",
                    "machine_id": "PressBrake_A",
                    "machine_model": "HG-1003",
                    "base_stroke": 120.5,
                    "correction_factor": 1.0,
                },
            },
            {
                "feature_id": "Hole_01",
                "feature_uid": f"{part_id}::Hole_01",
                "type": "HoleRadius",
                "target_value": 5.0,
                "unit": "mm",
                "tolerance": {
                    "is_explicit": True,
                    "upper": 0.05,
                    "lower": -0.05,
                    "type": "symmetric"
                },
                "bbox": [500, 500, 550, 550],
            },
        ],
    }


def extract_features(
    image_path: str,
    part_id: Optional[str] = None,
    client: Optional[OpenAI] = None,
    model: Optional[str] = None,
    settings: Optional[Settings] = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """
    Run VLM-based extraction. Falls back to a deterministic mock when the API key is absent.
    
    Supports:
    - Image formats: PNG, JPG, JPEG, WEBP, GIF
    - PDF files: Automatically converts first page to image (requires pdf2image)
    """
    settings = settings or load_settings()
    img_path = Path(image_path)
    resolved_part_id = part_id or img_path.stem

    # Check if file exists
    if not img_path.exists():
        raise FileNotFoundError(f"File not found: {image_path}")

    if not settings.openai.api_key:
        if strict:
            raise ValueError("Online feature extraction failed; mock fallback is disabled. Missing OPENAI_API_KEY.")
        print(f"Warning: No API key found. Using mock extraction for {img_path.name}")
        return _mock_extraction(resolved_part_id)

    # Check PDF support
    if img_path.suffix.lower() == '.pdf' and not PDF_SUPPORT:
        if strict:
            raise ValueError("Online feature extraction failed; mock fallback is disabled. PDF support is unavailable.")
        print("Warning: PDF support not available. Install with: pip install pdf2image Pillow")
        print("Falling back to mock extraction.")
        return _mock_extraction(resolved_part_id)

    client = client or build_openai_client(settings)
    vlm_model = model or settings.openai.model

    try:
        b64_image = _encode_image_to_base64(img_path)
        
        # Determine image format for API
        if img_path.suffix.lower() == '.pdf':
            image_format = "png"  # PDF converted to PNG
        else:
            image_format = img_path.suffix.lower().lstrip('.')
        
        user_content = [
            {"type": "text", "text": "Extract all geometric features and tolerances."},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/{image_format};base64,{b64_image}"},
            },
        ]

        response = client.chat.completions.create(
            model=vlm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=16384,  # Raise limit to reduce truncation risk
        )

        content = response.choices[0].message.content
        
        # Check if response is too long (potential truncation)
        if len(content) > 25000:
            print(f"Warning: Very long response ({len(content)} chars), may be truncated or overly detailed")
        
        # Use robust JSON parsing
        try:
            payload = _parse_json_robust(content)
        except Exception as parse_error:
            print(f"Warning: JSON parsing failed after all strategies: {parse_error}")
            print(f"Raw response length: {len(content)} chars")
            if len(content) < 1000:
                print(f"Raw response: {content}")
            else:
                print(f"Raw response start: {content[:500]}...")
                print(f"Raw response end: ...{content[-500:]}")
            raise
        
        payload.setdefault("part_id", resolved_part_id)
        return payload
    
    except Exception as e:
        if strict:
            raise RuntimeError("Online feature extraction failed; mock fallback is disabled.") from e
        print(f"Warning: VLM extraction failed: {e}")
        print("Falling back to mock extraction.")
        return _mock_extraction(resolved_part_id)


def extract_header_metadata(
    image_path: str,
    client: Optional[OpenAI] = None,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """
    Extract metadata from drawing header/title block using VLM.
    Useful for complex drawings where header needs separate processing.
    
    Supports PDF files (automatically converted to images).
    """
    settings = settings or load_settings()
    
    if not settings.openai.api_key:
        return {}
    
    img_path = Path(image_path)
    if img_path.suffix.lower() == '.pdf' and not PDF_SUPPORT:
        print("Warning: PDF support not available for header extraction")
        return {}
    
    client = client or build_openai_client(settings)
    vlm_model = settings.openai.model
    
    try:
        b64_image = _encode_image_to_base64(img_path)
        
        # Determine image format
        if img_path.suffix.lower() == '.pdf':
            image_format = "png"
        else:
            image_format = img_path.suffix.lower().lstrip('.')
        
        response = client.chat.completions.create(
            model=vlm_model,
            messages=[
                {"role": "system", "content": HEADER_EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract metadata from the title block and header area."
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{image_format};base64,{b64_image}"}
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=8192,
        )
        
        content = response.choices[0].message.content
        return _parse_json_robust(content)
    except Exception as e:
        print(f"Warning: Header extraction failed: {e}")
        return {}


def extract_gdt_specifications(
    image_path: str,
    client: Optional[OpenAI] = None,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """
    Extract GD&T (Geometric Dimensioning and Tolerancing) specifications.
    Focuses on position tolerances, datums, and geometric callouts.
    
    Supports PDF files (automatically converted to images).
    """
    settings = settings or load_settings()
    
    if not settings.openai.api_key:
        return {"gdt_callouts": []}
    
    img_path = Path(image_path)
    if img_path.suffix.lower() == '.pdf' and not PDF_SUPPORT:
        print("Warning: PDF support not available for GD&T extraction")
        return {"gdt_callouts": []}
    
    client = client or build_openai_client(settings)
    vlm_model = settings.openai.model
    
    try:
        b64_image = _encode_image_to_base64(img_path)
        
        # Determine image format
        if img_path.suffix.lower() == '.pdf':
            image_format = "png"
        else:
            image_format = img_path.suffix.lower().lstrip('.')
        
        response = client.chat.completions.create(
            model=vlm_model,
            messages=[
                {"role": "system", "content": GDT_EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract all GD&T callouts and geometric tolerances from this drawing."
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{image_format};base64,{b64_image}"}
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=8192,
        )
        
        content = response.choices[0].message.content
        return _parse_json_robust(content)
    except Exception as e:
        print(f"Warning: GD&T extraction failed: {e}")
        return {"gdt_callouts": []}


def extract_features_advanced(
    image_path: str,
    part_id: Optional[str] = None,
    client: Optional[OpenAI] = None,
    settings: Optional[Settings] = None,
    extract_metadata: bool = True,
    extract_gdt: bool = True,
    strict: bool = False,
) -> Dict[str, Any]:
    """
    Advanced extraction with multi-stage processing:
    1. Header/metadata extraction
    2. Main feature extraction
    3. GD&T specification extraction
    
    Combines all results into a comprehensive extraction payload.
    """
    settings = settings or load_settings()
    client = client or build_openai_client(settings) if settings.openai.api_key else None
    
    # Stage 1: Extract main features
    features_data = extract_features(image_path, part_id, client, None, settings, strict=strict)
    
    # Stage 2: Extract header metadata (if requested)
    if extract_metadata and client:
        metadata = extract_header_metadata(image_path, client, settings)
        features_data.update({
            "part_number": metadata.get("part_number", features_data.get("part_id")),
            "material": metadata.get("material"),
            "material_state": metadata.get("material_state"),
            "scale": metadata.get("scale"),
            "unfolded_dimensions": metadata.get("unfolded_dimensions"),
        })
    
    # Stage 3: Extract GD&T (if requested)
    if extract_gdt and client:
        try:
            gdt_data = extract_gdt_specifications(image_path, client, settings)
            
            # Handle different return types
            if isinstance(gdt_data, dict):
                gdt_callouts = gdt_data.get("gdt_callouts", [])
            elif isinstance(gdt_data, list):
                # Sometimes VLM returns list directly
                gdt_callouts = gdt_data
            else:
                gdt_callouts = []
            
            # Merge GD&T data into features
            for callout in gdt_callouts:
                if not isinstance(callout, dict):
                    continue
                applied_to = callout.get("applied_to")
                if applied_to:
                    # Find matching feature and add GD&T info
                    for feature in features_data.get("features", []):
                        if feature.get("feature_id") == applied_to:
                            feature["gdt"] = {
                                "type": callout.get("type"),
                                "value": callout.get("value"),
                                "datums": callout.get("datums", [])
                            }
            
            # Also store raw GD&T callouts
            features_data["gdt_callouts"] = gdt_callouts
        except Exception as e:
            print(f"Warning: GD&T processing failed: {e}")
            features_data["gdt_callouts"] = []
    
    return features_data

