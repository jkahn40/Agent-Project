"""Unit tests for the job description parser."""

import json
from unittest.mock import MagicMock

import pytest

from src.job_parser import JobDescriptionParser
from src.models import JobRequirements, SeniorityLevel

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_JOB_DESCRIPTION = """
Senior Backend Engineer — Fintech Startup

We're looking for a Senior Backend Engineer to join our growing team.

Requirements:
- 5+ years of experience with Python or Go
- Strong experience with PostgreSQL and Redis
- Experience building RESTful APIs and microservices
- Familiarity with AWS (EC2, Lambda, S3)
- Experience with Docker and Kubernetes

Nice to have:
- Experience with event-driven architectures (Kafka, RabbitMQ)
- Knowledge of financial systems or payment processing
- Contributions to open source projects

Location: San Francisco, CA (Hybrid)
"""

MOCK_PARSE_RESPONSE = json.dumps(
    {
        "title": "Senior Backend Engineer",
        "seniority": "senior",
        "required_skills": ["Python", "Go", "PostgreSQL", "Redis", "AWS", "Docker", "Kubernetes"],
        "preferred_skills": ["Kafka", "RabbitMQ", "Financial Systems"],
        "min_years_experience": 5,
        "industry_keywords": ["fintech", "payments"],
        "location": "San Francisco, CA",
        "education": None,
        "summary": (
            "A senior backend engineer with 5+ years of experience in Python/Go, "
            "strong database and cloud skills, ideally with fintech domain knowledge."
        ),
    }
)

MOCK_CRITERIA_RESPONSE = json.dumps(
    {
        "keywords": ["Python backend engineer", "Go microservices", "fintech engineer"],
        "titles": ["Senior Backend Engineer", "Senior Software Engineer", "Staff Engineer"],
        "locations": ["San Francisco, CA", "Bay Area"],
        "companies": [],
        "industries": ["Financial Technology", "Payments"],
        "current_only": False,
    }
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestJobDescriptionParser:
    def _make_parser_with_mock(self, response_text: str) -> JobDescriptionParser:
        """Create a parser with a mocked Anthropic client."""
        parser = JobDescriptionParser.__new__(JobDescriptionParser)
        parser.model = "claude-sonnet-4-20250514"

        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_content = MagicMock()
        mock_content.text = response_text
        mock_message.content = [mock_content]
        mock_client.messages.create.return_value = mock_message

        parser.client = mock_client
        return parser

    def test_parse_job_description(self):
        parser = self._make_parser_with_mock(MOCK_PARSE_RESPONSE)
        result = parser.parse_job_description(SAMPLE_JOB_DESCRIPTION)

        assert isinstance(result, JobRequirements)
        assert result.title == "Senior Backend Engineer"
        assert result.seniority == SeniorityLevel.SENIOR
        assert "Python" in result.required_skills
        assert result.min_years_experience == 5
        assert result.location == "San Francisco, CA"

    def test_parse_with_markdown_fences(self):
        wrapped = f"```json\n{MOCK_PARSE_RESPONSE}\n```"
        parser = self._make_parser_with_mock(wrapped)
        result = parser.parse_job_description(SAMPLE_JOB_DESCRIPTION)
        assert result.title == "Senior Backend Engineer"

    def test_derive_search_criteria(self):
        parser = self._make_parser_with_mock(MOCK_CRITERIA_RESPONSE)
        requirements = JobRequirements(
            title="Senior Backend Engineer",
            seniority=SeniorityLevel.SENIOR,
            required_skills=["Python", "Go"],
            summary="A senior backend engineer.",
        )
        criteria = parser.derive_search_criteria(requirements)
        assert len(criteria.keywords) > 0
        assert len(criteria.titles) > 0
        assert criteria.current_only is False

    def test_extract_json_plain(self):
        data = JobDescriptionParser._extract_json('{"key": "value"}')
        assert data == {"key": "value"}

    def test_extract_json_with_fences(self):
        text = '```json\n{"key": "value"}\n```'
        data = JobDescriptionParser._extract_json(text)
        assert data == {"key": "value"}

    def test_extract_json_invalid_raises(self):
        with pytest.raises(json.JSONDecodeError):
            JobDescriptionParser._extract_json("not json at all")
