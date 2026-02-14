"""Claude Cowork integration — run the candidate finder as a tool within a
Claude conversation loop.

This module implements a "Cowork agent" pattern where Claude acts as an
orchestrator that can call the candidate-finder tools to help users source
candidates interactively.

Usage:
    from src.cowork import CoworkSession
    session = CoworkSession()
    session.run_interactive()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

import anthropic
from dotenv import load_dotenv

from src.agent import CandidateFinderAgent
from src.models import FindCandidatesRequest
from tools.definitions import ALL_TOOLS

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt for the Cowork orchestrator
# ---------------------------------------------------------------------------

COWORK_SYSTEM = """\
You are a senior technical recruiter assistant working inside Claude Cowork.
You help users find candidates for open positions by analysing job descriptions
and searching LinkedIn.

You have access to two specialised tools:

1. **find_linkedin_candidates** — the full pipeline: parse a JD, search LinkedIn,
   and return ranked candidates.  Use this when the user provides (or you can
   construct) a full job description.

2. **parse_job_description** — parse a JD into structured requirements without
   searching.  Use this when the user wants to review / refine requirements
   before launching a search.

Workflow:
- When the user provides a job description, first confirm the key requirements
  with them (you can use parse_job_description for this).
- Once confirmed, use find_linkedin_candidates to run the full search.
- Present results in a clear, actionable format.
- Offer to refine the search if the user isn't satisfied.

Be concise, professional, and proactive.  Ask clarifying questions when the
job description is ambiguous.
"""


# ---------------------------------------------------------------------------
# Cowork Session
# ---------------------------------------------------------------------------


class CoworkSession:
    """Interactive session that lets Claude use the candidate-finder tools."""

    def __init__(
        self,
        anthropic_api_key: Optional[str] = None,
        model: str | None = None,
    ):
        self.api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY required")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.agent = CandidateFinderAgent(anthropic_api_key=self.api_key, model=self.model)
        self.messages: list[dict] = []

    async def chat(self, user_message: str) -> str:
        """Send a user message and process the response (including tool calls)."""
        self.messages.append({"role": "user", "content": user_message})

        # Conversation loop — keep going while the model wants to use tools
        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=COWORK_SYSTEM,
                tools=ALL_TOOLS,
                messages=self.messages,
            )

            # Collect all content blocks
            assistant_content = response.content
            self.messages.append({"role": "assistant", "content": assistant_content})

            # Check if the model wants to use tools
            tool_uses = [b for b in assistant_content if b.type == "tool_use"]

            if not tool_uses:
                # No tool calls — extract text and return
                text_parts = [b.text for b in assistant_content if hasattr(b, "text")]
                return "\n".join(text_parts)

            # Process each tool call
            tool_results = []
            for tool_use in tool_uses:
                result_text = await self._execute_tool(tool_use.name, tool_use.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_text,
                    }
                )

            self.messages.append({"role": "user", "content": tool_results})

    async def _execute_tool(self, name: str, args: dict) -> str:
        """Execute a tool call and return the result as a string."""
        logger.info("Executing tool: %s", name)

        try:
            if name == "find_linkedin_candidates":
                request = FindCandidatesRequest(
                    job_description=args["job_description"],
                    max_candidates=args.get("max_candidates", 10),
                    location_filter=args.get("location_filter"),
                )
                result = await self.agent.find_candidates(request)
                return result.model_dump_json(indent=2)

            elif name == "parse_job_description":
                requirements = self.agent.parser.parse_job_description(
                    args["job_description"]
                )
                criteria = self.agent.parser.derive_search_criteria(requirements)
                return json.dumps(
                    {
                        "requirements": requirements.model_dump(),
                        "search_criteria": criteria.model_dump(),
                    },
                    indent=2,
                    default=str,
                )

            else:
                return json.dumps({"error": f"Unknown tool: {name}"})

        except Exception as exc:
            logger.exception("Tool %s failed", name)
            return json.dumps({"error": str(exc)})

    def run_interactive(self) -> None:
        """Run an interactive terminal session."""
        print("=" * 60)
        print("  LinkedIn Candidate Finder — Claude Cowork Session")
        print("  Type 'quit' or 'exit' to end the session.")
        print("=" * 60)
        print()

        async def _loop():
            while True:
                try:
                    user_input = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye!")
                    break

                if not user_input:
                    continue
                if user_input.lower() in ("quit", "exit"):
                    print("Goodbye!")
                    break

                print("\nAssistant: ", end="", flush=True)
                response = await self.chat(user_input)
                print(response)
                print()

        asyncio.run(_loop())


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    session = CoworkSession()
    session.run_interactive()


if __name__ == "__main__":
    main()
