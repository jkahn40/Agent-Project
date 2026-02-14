"""Unit tests for data models."""

import pytest
from pydantic import ValidationError

from src.models import (
    CandidateMatch,
    CandidateProfile,
    Education,
    Experience,
    FindCandidatesRequest,
    FindCandidatesResponse,
    JobRequirements,
    SearchCriteria,
    SeniorityLevel,
)


class TestJobRequirements:
    def test_basic_creation(self):
        req = JobRequirements(
            title="Senior Backend Engineer",
            seniority=SeniorityLevel.SENIOR,
            required_skills=["Python", "PostgreSQL", "AWS"],
            preferred_skills=["Go", "Kubernetes"],
            min_years_experience=5,
            location="San Francisco, CA",
            summary="Looking for a senior backend engineer with cloud experience.",
        )
        assert req.title == "Senior Backend Engineer"
        assert req.seniority == SeniorityLevel.SENIOR
        assert len(req.required_skills) == 3
        assert req.min_years_experience == 5

    def test_optional_fields_default_to_none(self):
        req = JobRequirements(
            title="Engineer",
            seniority=SeniorityLevel.MID,
            summary="A mid-level engineer.",
        )
        assert req.min_years_experience is None
        assert req.location is None
        assert req.education is None
        assert req.required_skills == []
        assert req.preferred_skills == []

    def test_serialization_roundtrip(self):
        req = JobRequirements(
            title="ML Engineer",
            seniority=SeniorityLevel.STAFF,
            required_skills=["PyTorch", "Python"],
            summary="Staff ML engineer.",
        )
        data = req.model_dump()
        restored = JobRequirements(**data)
        assert restored == req

    def test_json_roundtrip(self):
        req = JobRequirements(
            title="ML Engineer",
            seniority=SeniorityLevel.STAFF,
            required_skills=["PyTorch"],
            summary="Staff ML engineer.",
        )
        json_str = req.model_dump_json()
        restored = JobRequirements.model_validate_json(json_str)
        assert restored == req


class TestSearchCriteria:
    def test_creation(self):
        sc = SearchCriteria(
            keywords=["python", "backend"],
            titles=["Backend Engineer", "Software Engineer"],
            locations=["San Francisco"],
        )
        assert len(sc.keywords) == 2
        assert sc.current_only is False

    def test_empty_optional_lists(self):
        sc = SearchCriteria(keywords=["test"], titles=["Test"])
        assert sc.locations == []
        assert sc.companies == []
        assert sc.industries == []


class TestCandidateProfile:
    def test_minimal_profile(self):
        p = CandidateProfile(
            name="Jane Doe",
            profile_url="https://www.linkedin.com/in/janedoe",
        )
        assert p.name == "Jane Doe"
        assert p.skills == []
        assert p.experience == []

    def test_full_profile(self):
        p = CandidateProfile(
            name="John Smith",
            headline="Senior Engineer at BigCo",
            location="New York, NY",
            profile_url="https://www.linkedin.com/in/johnsmith",
            current_company="BigCo",
            current_title="Senior Engineer",
            skills=["Python", "Go", "AWS"],
            experience=[
                Experience(
                    title="Senior Engineer",
                    company="BigCo",
                    duration="3 years",
                ),
                Experience(
                    title="Engineer",
                    company="StartupCo",
                    duration="2 years",
                ),
            ],
            education=[
                Education(
                    school="MIT",
                    degree="BS",
                    field_of_study="Computer Science",
                )
            ],
        )
        assert len(p.experience) == 2
        assert len(p.education) == 1
        assert p.skills == ["Python", "Go", "AWS"]


class TestCandidateMatch:
    def test_score_validation(self):
        profile = CandidateProfile(
            name="Test", profile_url="https://linkedin.com/in/test"
        )
        match = CandidateMatch(
            candidate=profile,
            overall_score=85.5,
            skill_match_score=90,
            experience_match_score=80,
            reasoning="Strong match.",
        )
        assert match.overall_score == 85.5

    def test_score_out_of_range(self):
        profile = CandidateProfile(
            name="Test", profile_url="https://linkedin.com/in/test"
        )
        with pytest.raises(ValidationError):
            CandidateMatch(
                candidate=profile,
                overall_score=150,  # > 100
                skill_match_score=90,
                experience_match_score=80,
                reasoning="Invalid.",
            )

    def test_score_negative(self):
        profile = CandidateProfile(
            name="Test", profile_url="https://linkedin.com/in/test"
        )
        with pytest.raises(ValidationError):
            CandidateMatch(
                candidate=profile,
                overall_score=-5,  # < 0
                skill_match_score=90,
                experience_match_score=80,
                reasoning="Invalid.",
            )


class TestFindCandidatesRequest:
    def test_defaults(self):
        req = FindCandidatesRequest(job_description="Build things.")
        assert req.max_candidates == 10
        assert req.location_filter is None

    def test_max_candidates_bounds(self):
        with pytest.raises(ValidationError):
            FindCandidatesRequest(job_description="test", max_candidates=0)
        with pytest.raises(ValidationError):
            FindCandidatesRequest(job_description="test", max_candidates=100)


class TestFindCandidatesResponse:
    def test_empty_response(self):
        resp = FindCandidatesResponse(
            job_requirements=JobRequirements(
                title="Test",
                seniority=SeniorityLevel.MID,
                summary="Test.",
            ),
            search_criteria=SearchCriteria(
                keywords=["test"], titles=["Test"]
            ),
        )
        assert resp.candidates == []
        assert resp.total_profiles_scanned == 0
