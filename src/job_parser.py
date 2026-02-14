"""Parse a free-text job description into structured requirements using Claude."""

from __future__ import annotations

import json
import logging
from typing import Optional

import anthropic

from src.models import JobRequirements, SearchCriteria

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PARSE_JOB_SYSTEM = """\
You are an expert technical recruiter and hiring analyst.
Your task is to extract structured information from a job description.
Return your answer as a single JSON object matching the schema below.
No markdown fences, no extra commentary.

JSON schema:
{
  "title": "<normalised job title>",
  "seniority": "<intern|junior|mid|senior|staff|principal|director|vp|c_level>",
  "required_skills": ["skill1", ...],
  "preferred_skills": ["skill1", ...],
  "min_years_experience": <int or null>,
  "industry_keywords": ["keyword1", ...],
  "location": "<location or 'Remote' or null>",
  "education": "<degree requirement or null>",
  "summary": "<one-paragraph summary of the ideal candidate>"
}
"""

SEARCH_CRITERIA_SYSTEM = """\
You are an expert sourcing strategist.  Given structured job requirements (JSON),
produce optimal LinkedIn search criteria to find matching candidates.
Return your answer as a single JSON object — no markdown fences, no extra commentary.

JSON schema:
{
  "keywords": ["keyword1", ...],
  "titles": ["title1", ...],
  "locations": ["location1", ...],
  "companies": ["company1", ...],
  "industries": ["industry1", ...],
  "current_only": <true|false>
}

Guidelines:
- Generate 3-5 keyword combinations that would surface good candidates.
- Include the exact job title plus 2-3 common alternate titles.
- For locations, include the stated location plus nearby tech hubs if relevant.
- Only include companies if the job description or industry makes specific ones obvious targets.
- Set current_only to false unless the role absolutely requires
  current employment in a specific title.
"""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class JobDescriptionParser:
    """Uses Claude to parse job descriptions into structured data."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    # ----- public API -----

    def parse_job_description(self, raw_text: str) -> JobRequirements:
        """Extract structured requirements from a raw job description."""
        logger.info("Parsing job description (%d chars) …", len(raw_text))

        message = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=PARSE_JOB_SYSTEM,
            messages=[{"role": "user", "content": raw_text}],
        )

        content = message.content[0].text
        data = self._extract_json(content)
        requirements = JobRequirements(**data)
        logger.info(
            "Parsed requirements: title=%s, seniority=%s",
            requirements.title,
            requirements.seniority,
        )
        return requirements

    def derive_search_criteria(self, requirements: JobRequirements) -> SearchCriteria:
        """Turn parsed requirements into LinkedIn search criteria."""
        logger.info("Deriving search criteria from requirements …")

        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SEARCH_CRITERIA_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": requirements.model_dump_json(indent=2),
                }
            ],
        )

        content = message.content[0].text
        data = self._extract_json(content)
        criteria = SearchCriteria(**data)
        logger.info(
            "Search criteria: %d keywords, %d titles, %d locations",
            len(criteria.keywords),
            len(criteria.titles),
            len(criteria.locations),
        )
        return criteria

    # ----- helpers -----

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Best-effort extraction of a JSON object from model output."""
        text = text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            first_newline = text.index("\n")
            last_fence = text.rfind("```")
            text = text[first_newline + 1 : last_fence].strip()
        return json.loads(text)
