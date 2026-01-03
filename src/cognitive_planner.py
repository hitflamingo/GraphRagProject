"""
Cognitive Planner: Bayesian risk-adaptive decision making for inspection.

Implements the Phase 2 prompt template to produce adaptive inspection plans
that respond to retrieved risk intelligence.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from openai import OpenAI

from .config import Settings, load_settings, build_openai_client


PROMPT_TEMPLATE = """
You are an Intelligent Quality Control Decision Agent.

# Context
- Feature: {feature_type} (Nominal: {nominal}, Explicit Tol: {tolerance})
- Process Step: {process_step}

# Risk Intelligence (Retrieved from Knowledge Graph)
- Risk Level: {risk_level}
- Historical Evidence: {risk_evidence}

# Standard Rules
- Rule 1: Use Vision System if Tol > 0.05mm.
- Rule 2: Use AQL 4.0 sampling for stable processes.

# Decision Task
Your goal is to optimize the inspection plan. 
IF risk is HIGH, you MUST override Standard Rules to reduce failure risk.
IF risk is LOW, you should prioritize cost efficiency.

# Output Format (JSON)
{{
  "method": "string (CMM | Vision System | Manual)",
  "sampling_rate": "string (100% | AQL 2.5 | AQL 4.0)",
  "dynamic_tolerance_adjustment": "string (e.g., 'Tighten to ±0.05mm due to history')",
  "reasoning_chain": "string (Explain why you deviated from standard rules based on risk)"
}}
"""


class CognitivePlanner:
    """
    Wrapper around the adaptive decision prompt with a safe fallback.
    """

    def __init__(
        self,
        client: Optional[OpenAI],
        settings: Optional[Settings] = None,
        failure_cost: float = 1000.0,
    ):
        self.settings = settings or load_settings()
        self.client = client or self._build_client()
        # Simple cost knobs; can be overriden via env in the future.
        self.cost_cmm = 10.0  # $/min
        self.cost_vision = 0.5  # $/min
        self.failure_cost = failure_cost

    # ------------------------------ Public API ------------------------------ #
    def plan_inspection(
        self, feature_context: Dict[str, Any], risk_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate adaptive inspection plan using LLM; fallback to deterministic rules.
        """
        tolerance = feature_context.get("tolerance", {})
        tol_upper = tolerance.get("upper")
        tol_lower = tolerance.get("lower")
        tol_str = f"+{tol_upper}/ {tol_lower}" if tol_upper is not None else "N/A"
        process_step = self._resolve_process_step(feature_context)
        risk_level = risk_context.get("level", "LOW")
        evidence = "; ".join(risk_context.get("evidence", [])) or "None"

        user_filled_prompt = PROMPT_TEMPLATE.format(
            feature_type=feature_context.get("type", "Unknown"),
            nominal=feature_context.get("target_value"),
            tolerance=tol_str,
            process_step=process_step,
            risk_level=risk_level,
            risk_evidence=evidence,
        )

        if self.client:
            try:
                response = self.client.chat.completions.create(
                    model=self.settings.openai.model,
                    messages=[
                        {"role": "system", "content": "You are a senior quality engineer."},
                        {"role": "user", "content": user_filled_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                return json.loads(response.choices[0].message.content)
            except Exception as e:
                print(f"Warning: Cognitive planner LLM failed, fallback used: {e}")

        return self._fallback_plan(feature_context, risk_level, evidence)

    # ------------------------------ Internals ------------------------------- #
    def _build_client(self) -> Optional[OpenAI]:
        if not self.settings.openai.api_key:
            return None
        try:
            return build_openai_client(self.settings)
        except Exception as e:
            print(f"Warning: Cannot initialize CognitivePlanner client: {e}")
            return None

    def _resolve_process_step(self, feature_context: Dict[str, Any]) -> str:
        process_steps = feature_context.get("process_steps") or []
        if process_steps and isinstance(process_steps[0], dict):
            return process_steps[0].get("name") or process_steps[0].get("process_name", "Unknown")
        if process_steps:
            return str(process_steps[0])
        if feature_context.get("process_step"):
            return str(feature_context["process_step"])
        return "Unknown"

    def _fallback_plan(
        self, feature_context: Dict[str, Any], risk_level: str, evidence: str
    ) -> Dict[str, Any]:
        """
        Deterministic heuristic mirroring the spec rules when LLM is unavailable.
        """
        tolerance = feature_context.get("tolerance", {})
        tol_upper = tolerance.get("upper")
        tol_lower = tolerance.get("lower")

        wide_tolerance = tol_upper is not None and tol_upper > 0.05
        method = "Vision System" if wide_tolerance else "CMM"
        sampling = "AQL 4.0"
        dynamic_adjustment = "Keep nominal tolerance"

        if risk_level in ("HIGH", "CRITICAL"):
            method = "CMM"
            sampling = "100%"
            dynamic_adjustment = "Tighten to ±0.05mm due to historical risk"
        elif wide_tolerance:
            sampling = "AQL 4.0"
        else:
            sampling = "AQL 2.5"

        return {
            "method": method,
            "sampling_rate": sampling,
            "dynamic_tolerance_adjustment": dynamic_adjustment,
            "reasoning_chain": f"Risk={risk_level}; evidence={evidence}",
        }

