"""Rank and score candidate profiles against job requirements using Claude."""

from __future__ import annotations

import json
import logging
from typing import Optional

import anthropic

from src.models import CandidateMatch, CandidateProfile, JobRequirements

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

RANKING_SYSTEM = """\
You are a senior technical recruiter evaluating candidate profiles against a job posting.
For each candidate, produce a JSON object with the following fields.
No markdown fences, no extra text.

JSON schema (respond with a JSON **array** of these objects, one per candidate):
{
  "profile_url": "<linkedin profile url>",
  "overall_score": <0-100>,
  "skill_match_score": <0-100>,
  "experience_match_score": <0-100>,
  "reasoning": "<2-3 sentence explanation>",
  "strengths": ["strength1", ...],
  "gaps": ["gap1", ...]
}

Scoring guidelines:
- 90-100: Near-perfect match — all required skills, matching seniority, relevant domain.
- 70-89: Strong match — most required skills, close seniority level.
- 50-69: Moderate match — several required skills present, may lack seniority or domain experience.
- 30-49: Weak match — few overlapping skills, significant gaps.
- 0-29: Poor match — minimal alignment with the role.

Be critical but fair.  Consider:
1. Required vs preferred skills overlap.
2. Seniority / years of experience alignment.
3. Industry and domain relevance.
4. Education fit (if relevant).
5. Current title / trajectory suggesting growth into the role.
"""


# ---------------------------------------------------------------------------
# Ranker
# ---------------------------------------------------------------------------


class CandidateRanker:
    """Uses Claude to evaluate and rank candidates against job requirements."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def rank_candidates(
        self,
        candidates: list[CandidateProfile],
        requirements: JobRequirements,
        batch_size: int = 5,
    ) -> list[CandidateMatch]:
        """Score and rank a list of candidates.  Returns sorted best→worst."""
        if not candidates:
            return []

        all_matches: list[CandidateMatch] = []

        # Process in batches to stay within context limits
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i : i + batch_size]
            logger.info(
                "Ranking batch %d–%d of %d candidates …",
                i + 1,
                min(i + batch_size, len(candidates)),
                len(candidates),
            )

            candidates_json = [
                c.model_dump(exclude_none=True) for c in batch
            ]

            user_msg = (
                "## Job Requirements\n\n"
                f"{requirements.model_dump_json(indent=2)}\n\n"
                "## Candidate Profiles\n\n"
                f"{json.dumps(candidates_json, indent=2)}\n\n"
                "Evaluate each candidate and return the JSON array."
            )

            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=RANKING_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )

            content = message.content[0].text
            scored = self._parse_scores(content, batch)
            all_matches.extend(scored)

        # Sort by overall score descending
        all_matches.sort(key=lambda m: m.overall_score, reverse=True)
        return all_matches

    # ----- helpers -----

    def _parse_scores(
        self,
        text: str,
        candidates: list[CandidateProfile],
    ) -> list[CandidateMatch]:
        """Parse Claude's JSON array of scores and map back to candidates."""
        text = text.strip()
        if text.startswith("```"):
            first_nl = text.index("\n")
            last_fence = text.rfind("```")
            text = text[first_nl + 1 : last_fence].strip()

        try:
            scores: list[dict] = json.loads(text)
        except json.JSONDecodeError:
            logger.error("Failed to parse ranking response as JSON")
            # Return unscored matches so we still have data
            return [
                CandidateMatch(
                    candidate=c,
                    overall_score=0,
                    skill_match_score=0,
                    experience_match_score=0,
                    reasoning="Scoring unavailable — could not parse LLM response.",
                )
                for c in candidates
            ]

        # Build a lookup from profile_url to score dict
        score_map: dict[str, dict] = {}
        for s in scores:
            url = s.get("profile_url", "")
            score_map[url] = s

        matches: list[CandidateMatch] = []
        for candidate in candidates:
            s = score_map.get(candidate.profile_url, {})
            matches.append(
                CandidateMatch(
                    candidate=candidate,
                    overall_score=s.get("overall_score", 0),
                    skill_match_score=s.get("skill_match_score", 0),
                    experience_match_score=s.get("experience_match_score", 0),
                    reasoning=s.get("reasoning", "No score available."),
                    strengths=s.get("strengths", []),
                    gaps=s.get("gaps", []),
                )
            )
        return matches
