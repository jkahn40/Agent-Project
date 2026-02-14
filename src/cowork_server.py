"""MCP (Model Context Protocol) server for Claude Cowork integration.

This exposes the LinkedIn Candidate Finder agent as a set of MCP tools
that Claude Desktop / Claude Cowork can discover and invoke.

Run with:
    python -m src.cowork_server
    # or
    candidate-finder-mcp
"""

from __future__ import annotations

import asyncio
import json
import logging

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

from src.agent import CandidateFinderAgent
from src.models import FindCandidatesRequest

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

app = Server("linkedin-candidate-finder")


def _get_agent() -> CandidateFinderAgent:
    """Create (or re-use) a CandidateFinderAgent instance."""
    return CandidateFinderAgent()


# ---------- Tool listing ----------


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Expose available tools to Claude Cowork."""
    return [
        Tool(
            name="find_linkedin_candidates",
            description=(
                "Analyse a job description and search LinkedIn to find "
                "potential candidates that match the requirements.  Returns "
                "a ranked list of candidate profiles with match scores and "
                "detailed reasoning for each match."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "job_description": {
                        "type": "string",
                        "description": (
                            "The full job description text to analyse.  "
                            "Include title, responsibilities, requirements, etc."
                        ),
                    },
                    "max_candidates": {
                        "type": "integer",
                        "description": "Maximum number of candidates to return (1-50).",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "location_filter": {
                        "type": "string",
                        "description": "Optional geographic constraint.",
                    },
                },
                "required": ["job_description"],
            },
        ),
        Tool(
            name="parse_job_description",
            description=(
                "Parse a job description into structured requirements "
                "(title, skills, seniority, etc.) without searching LinkedIn. "
                "Useful for reviewing requirements before a full search."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "job_description": {
                        "type": "string",
                        "description": "The full job description text.",
                    },
                },
                "required": ["job_description"],
            },
        ),
        Tool(
            name="search_linkedin_candidates",
            description=(
                "Search LinkedIn for candidate profiles matching specific "
                "search criteria (keywords, titles, locations).  Lower-level "
                "than find_linkedin_candidates — use this when you already "
                "have structured search terms."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Search keywords.",
                    },
                    "titles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Job titles to search for.",
                    },
                    "locations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Geographic locations.",
                        "default": [],
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max profiles to return.",
                        "default": 10,
                    },
                },
                "required": ["keywords", "titles"],
            },
        ),
    ]


# ---------- Tool dispatch ----------


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool invocations from Claude Cowork."""
    logger.info("Tool call: %s(%s)", name, json.dumps(arguments)[:200])

    try:
        if name == "find_linkedin_candidates":
            return await _handle_find_candidates(arguments)
        elif name == "parse_job_description":
            return await _handle_parse_jd(arguments)
        elif name == "search_linkedin_candidates":
            return await _handle_search(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return [
            TextContent(
                type="text",
                text=f"Error running {name}: {exc}",
            )
        ]


async def _handle_find_candidates(args: dict) -> list[TextContent]:
    agent = _get_agent()
    request = FindCandidatesRequest(
        job_description=args["job_description"],
        max_candidates=args.get("max_candidates", 10),
        location_filter=args.get("location_filter"),
    )
    result = await agent.find_candidates(request)

    # Build a human-friendly + machine-readable response
    lines: list[str] = []
    lines.append(f"## Job: {result.job_requirements.title}")
    lines.append(f"**Seniority:** {result.job_requirements.seniority.value}")
    lines.append(f"**Required skills:** {', '.join(result.job_requirements.required_skills)}")
    lines.append(f"**Location:** {result.job_requirements.location or 'Not specified'}")
    lines.append("")
    lines.append(f"Scanned **{result.total_profiles_scanned}** profiles.  "
                 f"Returning top **{len(result.candidates)}** matches.\n")

    for i, match in enumerate(result.candidates, 1):
        c = match.candidate
        lines.append(f"### #{i} — {c.name}  (Score: {match.overall_score:.0f}/100)")
        if c.headline:
            lines.append(f"- **Headline:** {c.headline}")
        if c.location:
            lines.append(f"- **Location:** {c.location}")
        lines.append(f"- **Profile:** {c.profile_url}")
        lines.append(f"- **Skills match:** {match.skill_match_score:.0f}/100  |  "
                     f"**Experience match:** {match.experience_match_score:.0f}/100")
        lines.append(f"- **Reasoning:** {match.reasoning}")
        if match.strengths:
            lines.append(f"- **Strengths:** {', '.join(match.strengths)}")
        if match.gaps:
            lines.append(f"- **Gaps:** {', '.join(match.gaps)}")
        lines.append("")

    return [TextContent(type="text", text="\n".join(lines))]


async def _handle_parse_jd(args: dict) -> list[TextContent]:
    agent = _get_agent()
    requirements = agent.parser.parse_job_description(args["job_description"])
    criteria = agent.parser.derive_search_criteria(requirements)

    output = {
        "requirements": requirements.model_dump(),
        "search_criteria": criteria.model_dump(),
    }
    return [
        TextContent(
            type="text",
            text=json.dumps(output, indent=2, default=str),
        )
    ]


async def _handle_search(args: dict) -> list[TextContent]:
    from src.models import SearchCriteria

    agent = _get_agent()
    criteria = SearchCriteria(
        keywords=args["keywords"],
        titles=args["titles"],
        locations=args.get("locations", []),
    )
    profiles, queries = await agent.crawler.search(
        criteria, max_results=args.get("max_results", 10)
    )
    output = {
        "queries_used": queries,
        "profiles_found": len(profiles),
        "profiles": [p.model_dump(exclude_none=True) for p in profiles],
    }
    return [
        TextContent(
            type="text",
            text=json.dumps(output, indent=2, default=str),
        )
    ]


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server over stdio."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    logger.info("Starting LinkedIn Candidate Finder MCP server …")
    asyncio.run(_run())


async def _run() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    main()
