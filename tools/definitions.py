"""Tool definitions for the LinkedIn Candidate Finder, formatted for Claude's tool-use API.

These definitions can be passed directly to ``anthropic.Anthropic().messages.create(tools=…)``
to let Claude use the candidate finder as a tool within a Cowork multi-agent session.
"""

from __future__ import annotations

FIND_CANDIDATES_TOOL = {
    "name": "find_linkedin_candidates",
    "description": (
        "Analyse a job description and search LinkedIn to find potential "
        "candidates that match the requirements.  Returns a ranked list of "
        "candidate profiles with match scores and reasoning.\n\n"
        "Use this tool when the user wants to:\n"
        "  - Source candidates for a role\n"
        "  - Find people on LinkedIn matching a job description\n"
        "  - Get a shortlist of potential hires for a position"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "job_description": {
                "type": "string",
                "description": (
                    "The full job description text to analyse.  "
                    "Can include title, responsibilities, requirements, etc."
                ),
            },
            "max_candidates": {
                "type": "integer",
                "description": "Maximum number of candidates to return (1-50, default 10).",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
            },
            "location_filter": {
                "type": "string",
                "description": "Optional geographic location to constrain the search.",
            },
        },
        "required": ["job_description"],
    },
}

PARSE_JOB_DESCRIPTION_TOOL = {
    "name": "parse_job_description",
    "description": (
        "Parse a job description into structured requirements without "
        "performing a LinkedIn search.  Useful for reviewing what the "
        "agent understands before launching a full candidate search."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "job_description": {
                "type": "string",
                "description": "The full job description text to analyse.",
            },
        },
        "required": ["job_description"],
    },
}

# All tools as a list — ready to pass to ``tools=`` in the API call.
ALL_TOOLS = [FIND_CANDIDATES_TOOL, PARSE_JOB_DESCRIPTION_TOOL]
