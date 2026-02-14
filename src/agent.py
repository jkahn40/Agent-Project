"""Main orchestrator for the LinkedIn Candidate Finder agent.

This module ties together:
  1. Job-description parsing  (``job_parser``)
  2. LinkedIn searching        (``linkedin_crawler``)
  3. Candidate ranking          (``candidate_ranker``)

It exposes a single high-level ``find_candidates()`` coroutine that accepts a
free-text job description and returns a ranked list of potential matches.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from dotenv import load_dotenv

from src.candidate_ranker import CandidateRanker
from src.job_parser import JobDescriptionParser
from src.linkedin_crawler import LinkedInCrawler
from src.models import (
    FindCandidatesRequest,
    FindCandidatesResponse,
)

load_dotenv()
logger = logging.getLogger(__name__)


class CandidateFinderAgent:
    """End-to-end agent: JD → parse → search → rank → results."""

    def __init__(
        self,
        anthropic_api_key: Optional[str] = None,
        linkedin_cookie: Optional[str] = None,
        model: str | None = None,
    ):
        api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        li_at = linkedin_cookie or os.getenv("LINKEDIN_LI_AT")
        model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY must be set as an environment variable "
                "or passed directly."
            )

        self.parser = JobDescriptionParser(api_key=api_key, model=model)
        self.crawler = LinkedInCrawler(li_at_cookie=li_at or None)
        self.ranker = CandidateRanker(api_key=api_key, model=model)

    async def find_candidates(
        self, request: FindCandidatesRequest
    ) -> FindCandidatesResponse:
        """Run the full pipeline for a job description.

        1. Parse the job description into structured requirements.
        2. Derive LinkedIn search criteria.
        3. Crawl LinkedIn for candidate profiles.
        4. Score and rank every candidate against the requirements.
        5. Return sorted results.
        """
        # Step 1 — Parse
        logger.info("Step 1/4 — Parsing job description …")
        requirements = self.parser.parse_job_description(request.job_description)

        # Step 2 — Derive search criteria
        logger.info("Step 2/4 — Deriving search criteria …")
        criteria = self.parser.derive_search_criteria(requirements)

        # Optional location override
        if request.location_filter:
            criteria.locations = [request.location_filter] + criteria.locations

        # Step 3 — Crawl
        logger.info("Step 3/4 — Searching LinkedIn …")
        profiles, queries_used = await self.crawler.search(
            criteria, max_results=request.max_candidates * 2  # over-fetch to allow ranking
        )
        logger.info("Found %d candidate profiles", len(profiles))

        # Step 4 — Rank
        logger.info("Step 4/4 — Ranking %d candidates …", len(profiles))
        ranked = self.ranker.rank_candidates(
            profiles, requirements
        )

        # Trim to requested number
        top = ranked[: request.max_candidates]

        return FindCandidatesResponse(
            job_requirements=requirements,
            search_criteria=criteria,
            candidates=top,
            total_profiles_scanned=len(profiles),
            search_queries_used=queries_used,
        )


# ---------------------------------------------------------------------------
# Convenience wrapper (sync)
# ---------------------------------------------------------------------------


def find_candidates_sync(
    job_description: str,
    max_candidates: int = 10,
    location_filter: Optional[str] = None,
    **agent_kwargs,
) -> FindCandidatesResponse:
    """Synchronous convenience wrapper around the async agent."""
    agent = CandidateFinderAgent(**agent_kwargs)
    request = FindCandidatesRequest(
        job_description=job_description,
        max_candidates=max_candidates,
        location_filter=location_filter,
    )
    return asyncio.run(agent.find_candidates(request))
