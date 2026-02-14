"""Pydantic data models for the LinkedIn Candidate Finder agent."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Job description models
# ---------------------------------------------------------------------------


class SeniorityLevel(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    DIRECTOR = "director"
    VP = "vp"
    C_LEVEL = "c_level"


class JobRequirements(BaseModel):
    """Structured requirements extracted from a free-text job description."""

    title: str = Field(description="Normalised job title, e.g. 'Senior Backend Engineer'")
    seniority: SeniorityLevel = Field(description="Inferred seniority level")
    required_skills: list[str] = Field(
        default_factory=list,
        description="Hard skills explicitly required (languages, frameworks, tools)",
    )
    preferred_skills: list[str] = Field(
        default_factory=list,
        description="Nice-to-have skills mentioned in the posting",
    )
    min_years_experience: Optional[int] = Field(
        default=None, description="Minimum years of experience if mentioned"
    )
    industry_keywords: list[str] = Field(
        default_factory=list,
        description="Domain / industry keywords (e.g. 'fintech', 'healthcare')",
    )
    location: Optional[str] = Field(
        default=None, description="Preferred location or 'Remote'"
    )
    education: Optional[str] = Field(
        default=None, description="Degree or education requirements if any"
    )
    summary: str = Field(
        description="One-paragraph human-readable summary of the ideal candidate"
    )


class SearchCriteria(BaseModel):
    """Search parameters derived from job requirements, used to query LinkedIn."""

    keywords: list[str] = Field(
        description="Primary search keywords to use on LinkedIn"
    )
    titles: list[str] = Field(
        description="Job titles to search for (current or past)"
    )
    locations: list[str] = Field(
        default_factory=list,
        description="Geographic locations to filter by",
    )
    companies: list[str] = Field(
        default_factory=list,
        description="Target companies to search within (optional)",
    )
    industries: list[str] = Field(
        default_factory=list,
        description="Industries to filter by",
    )
    current_only: bool = Field(
        default=False,
        description="Whether to only match current positions",
    )


# ---------------------------------------------------------------------------
# Candidate models
# ---------------------------------------------------------------------------


class Experience(BaseModel):
    """A single work-experience entry from a LinkedIn profile."""

    title: str
    company: str
    location: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None


class Education(BaseModel):
    """A single education entry from a LinkedIn profile."""

    school: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    years: Optional[str] = None


class CandidateProfile(BaseModel):
    """Represents a LinkedIn candidate profile."""

    name: str
    headline: Optional[str] = None
    location: Optional[str] = None
    profile_url: str
    connection_degree: Optional[str] = None
    current_company: Optional[str] = None
    current_title: Optional[str] = None
    summary: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)


class CandidateMatch(BaseModel):
    """A scored candidate with reasoning for why they match."""

    candidate: CandidateProfile
    overall_score: float = Field(
        ge=0, le=100, description="0-100 match score"
    )
    skill_match_score: float = Field(
        ge=0, le=100, description="How well skills align"
    )
    experience_match_score: float = Field(
        ge=0, le=100, description="How well experience level aligns"
    )
    reasoning: str = Field(description="Human-readable explanation of the score")
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent I/O
# ---------------------------------------------------------------------------


class FindCandidatesRequest(BaseModel):
    """Top-level request to the candidate-finder agent."""

    job_description: str = Field(
        description="Raw job description text to analyse"
    )
    max_candidates: int = Field(
        default=10, ge=1, le=50, description="Max number of candidates to return"
    )
    location_filter: Optional[str] = Field(
        default=None, description="Optional extra location constraint"
    )


class FindCandidatesResponse(BaseModel):
    """Top-level response from the candidate-finder agent."""

    job_requirements: JobRequirements
    search_criteria: SearchCriteria
    candidates: list[CandidateMatch] = Field(default_factory=list)
    total_profiles_scanned: int = 0
    search_queries_used: list[str] = Field(default_factory=list)
