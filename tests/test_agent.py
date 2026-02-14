"""Integration-style tests for the main CandidateFinderAgent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent import CandidateFinderAgent
from src.models import (
    CandidateMatch,
    CandidateProfile,
    FindCandidatesRequest,
    JobRequirements,
    SearchCriteria,
    SeniorityLevel,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_REQUIREMENTS = JobRequirements(
    title="Senior Backend Engineer",
    seniority=SeniorityLevel.SENIOR,
    required_skills=["Python", "PostgreSQL"],
    summary="Senior backend engineer.",
)

MOCK_CRITERIA = SearchCriteria(
    keywords=["Python backend"],
    titles=["Senior Backend Engineer"],
    locations=["San Francisco"],
)

MOCK_PROFILES = [
    CandidateProfile(
        name="Alice Strong",
        headline="Senior Engineer",
        profile_url="https://www.linkedin.com/in/alice-strong",
        skills=["Python", "PostgreSQL"],
    ),
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCandidateFinderAgent:
    @pytest.mark.asyncio
    async def test_find_candidates_pipeline(self):
        """Test the full pipeline with mocked components."""
        agent = CandidateFinderAgent.__new__(CandidateFinderAgent)

        # Mock parser
        agent.parser = MagicMock()
        agent.parser.parse_job_description.return_value = MOCK_REQUIREMENTS
        agent.parser.derive_search_criteria.return_value = MOCK_CRITERIA

        # Mock crawler
        agent.crawler = MagicMock()
        agent.crawler.search = AsyncMock(return_value=(MOCK_PROFILES, ["Python backend"]))

        # Mock ranker
        mock_match = CandidateMatch(
            candidate=MOCK_PROFILES[0],
            overall_score=85,
            skill_match_score=90,
            experience_match_score=80,
            reasoning="Strong match.",
        )
        agent.ranker = MagicMock()
        agent.ranker.rank_candidates.return_value = [mock_match]

        request = FindCandidatesRequest(
            job_description="Looking for a senior backend engineer with Python.",
            max_candidates=5,
        )

        result = await agent.find_candidates(request)

        # Verify pipeline was called correctly
        agent.parser.parse_job_description.assert_called_once()
        agent.parser.derive_search_criteria.assert_called_once_with(MOCK_REQUIREMENTS)
        agent.crawler.search.assert_called_once()
        agent.ranker.rank_candidates.assert_called_once()

        assert result.job_requirements == MOCK_REQUIREMENTS
        assert result.search_criteria == MOCK_CRITERIA
        assert len(result.candidates) == 1

    @pytest.mark.asyncio
    async def test_location_filter_prepended(self):
        """Location filter from request should be prepended to criteria."""
        agent = CandidateFinderAgent.__new__(CandidateFinderAgent)

        agent.parser = MagicMock()
        agent.parser.parse_job_description.return_value = MOCK_REQUIREMENTS
        agent.parser.derive_search_criteria.return_value = SearchCriteria(
            keywords=["test"],
            titles=["Test"],
            locations=["Original"],
        )
        agent.crawler = MagicMock()
        agent.crawler.search = AsyncMock(return_value=([], []))
        agent.ranker = MagicMock()
        agent.ranker.rank_candidates.return_value = []

        request = FindCandidatesRequest(
            job_description="test",
            location_filter="New York",
        )

        result = await agent.find_candidates(request)

        # The search criteria should have New York prepended
        assert result.search_criteria.locations[0] == "New York"
        assert "Original" in result.search_criteria.locations

    def test_init_requires_api_key(self):
        """Agent should raise if no API key is available."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                CandidateFinderAgent(anthropic_api_key=None)
