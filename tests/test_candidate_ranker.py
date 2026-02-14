"""Unit tests for the candidate ranker."""

import json
from unittest.mock import MagicMock

from src.candidate_ranker import CandidateRanker
from src.models import (
    CandidateMatch,
    CandidateProfile,
    JobRequirements,
    SeniorityLevel,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_REQUIREMENTS = JobRequirements(
    title="Senior Backend Engineer",
    seniority=SeniorityLevel.SENIOR,
    required_skills=["Python", "PostgreSQL", "AWS"],
    preferred_skills=["Go", "Kubernetes"],
    min_years_experience=5,
    summary="A senior backend engineer with cloud experience.",
)

SAMPLE_CANDIDATES = [
    CandidateProfile(
        name="Alice Strong",
        headline="Senior Software Engineer at BigTech",
        profile_url="https://www.linkedin.com/in/alice-strong",
        skills=["Python", "PostgreSQL", "AWS", "Docker"],
    ),
    CandidateProfile(
        name="Bob Weak",
        headline="Junior Frontend Developer",
        profile_url="https://www.linkedin.com/in/bob-weak",
        skills=["JavaScript", "React"],
    ),
]

MOCK_RANKING_RESPONSE = json.dumps(
    [
        {
            "profile_url": "https://www.linkedin.com/in/alice-strong",
            "overall_score": 88,
            "skill_match_score": 92,
            "experience_match_score": 85,
            "reasoning": "Strong Python and AWS skills with senior experience.",
            "strengths": ["Python expert", "AWS certified"],
            "gaps": ["No Go experience"],
        },
        {
            "profile_url": "https://www.linkedin.com/in/bob-weak",
            "overall_score": 25,
            "skill_match_score": 10,
            "experience_match_score": 20,
            "reasoning": "Frontend-focused with no backend experience.",
            "strengths": [],
            "gaps": ["No Python", "No backend", "Junior level"],
        },
    ]
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCandidateRanker:
    def _make_ranker_with_mock(self, response_text: str) -> CandidateRanker:
        ranker = CandidateRanker.__new__(CandidateRanker)
        ranker.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_content = MagicMock()
        mock_content.text = response_text
        mock_message.content = [mock_content]
        mock_client.messages.create.return_value = mock_message

        ranker.client = mock_client
        return ranker

    def test_rank_candidates(self):
        ranker = self._make_ranker_with_mock(MOCK_RANKING_RESPONSE)
        matches = ranker.rank_candidates(SAMPLE_CANDIDATES, SAMPLE_REQUIREMENTS)

        assert len(matches) == 2
        assert all(isinstance(m, CandidateMatch) for m in matches)
        # Should be sorted by score (best first)
        assert matches[0].overall_score >= matches[1].overall_score
        assert matches[0].candidate.name == "Alice Strong"
        assert matches[1].candidate.name == "Bob Weak"

    def test_rank_empty_list(self):
        ranker = self._make_ranker_with_mock("[]")
        matches = ranker.rank_candidates([], SAMPLE_REQUIREMENTS)
        assert matches == []

    def test_rank_handles_invalid_json_gracefully(self):
        ranker = self._make_ranker_with_mock("not valid json {{{")
        matches = ranker.rank_candidates(SAMPLE_CANDIDATES, SAMPLE_REQUIREMENTS)

        # Should still return candidates, but with zero scores
        assert len(matches) == 2
        assert all(m.overall_score == 0 for m in matches)
        assert "could not parse" in matches[0].reasoning.lower()

    def test_rank_handles_markdown_fences(self):
        wrapped = f"```json\n{MOCK_RANKING_RESPONSE}\n```"
        ranker = self._make_ranker_with_mock(wrapped)
        matches = ranker.rank_candidates(SAMPLE_CANDIDATES, SAMPLE_REQUIREMENTS)
        assert len(matches) == 2
        assert matches[0].overall_score == 88

    def test_parse_scores_maps_correctly(self):
        ranker = self._make_ranker_with_mock(MOCK_RANKING_RESPONSE)
        matches = ranker._parse_scores(MOCK_RANKING_RESPONSE, SAMPLE_CANDIDATES)

        alice = next(m for m in matches if m.candidate.name == "Alice Strong")
        assert alice.overall_score == 88
        assert alice.skill_match_score == 92
        assert "Python expert" in alice.strengths

        bob = next(m for m in matches if m.candidate.name == "Bob Weak")
        assert bob.overall_score == 25
        assert "No Python" in bob.gaps
