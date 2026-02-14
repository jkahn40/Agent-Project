# LinkedIn Candidate Finder

An AI agent that reviews job descriptions and crawls LinkedIn to find potential candidates, integrated with **Claude Cowork** via the Model Context Protocol (MCP).

## How It Works

The agent runs a four-step pipeline:

1. **Parse** -- Claude analyses a free-text job description and extracts structured requirements (title, seniority, required/preferred skills, location, experience level, etc.).
2. **Plan** -- Claude derives optimal LinkedIn search criteria (keywords, titles, locations, target companies) from the structured requirements.
3. **Search** -- The crawler searches LinkedIn for matching profiles.  It supports two strategies:
   - **Authenticated search** using the LinkedIn Voyager API (requires a session cookie).
   - **Google X-Ray search** (`site:linkedin.com/in`) as an unauthenticated fallback.
4. **Rank** -- Claude evaluates every discovered profile against the job requirements and returns a scored, sorted shortlist with detailed reasoning.

## Project Structure

```
.
├── src/
│   ├── models.py            # Pydantic data models
│   ├── job_parser.py         # JD → structured requirements (Claude)
│   ├── linkedin_crawler.py   # LinkedIn search (Voyager API + Google X-Ray)
│   ├── candidate_ranker.py   # Candidate scoring (Claude)
│   ├── agent.py              # Main orchestrator
│   ├── cli.py                # Command-line interface
│   ├── cowork.py             # Interactive Claude Cowork session
│   └── cowork_server.py      # MCP server for Claude Desktop / Cowork
├── tools/
│   └── definitions.py        # Tool schemas for Claude tool-use API
├── tests/                    # 37 unit tests
├── claude_cowork_config.json # MCP server config for Claude Desktop
├── pyproject.toml
├── requirements.txt
└── .env.example
```

## Quick Start

### 1. Install

```bash
pip install -e ".[dev]"
```

### 2. Configure

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `LINKEDIN_LI_AT` | No | LinkedIn session cookie for authenticated search (see below) |
| `ANTHROPIC_MODEL` | No | Model to use (default: `claude-sonnet-4-20250514`) |

**Getting the LinkedIn cookie:** Log in to LinkedIn in your browser, open DevTools > Application > Cookies > `linkedin.com`, and copy the value of the `li_at` cookie.  Without it the agent falls back to Google X-Ray search, which returns fewer results.

### 3. Run

#### Command Line

```bash
# From a file
candidate-finder -f job_description.txt

# Inline
candidate-finder "We are looking for a Senior Backend Engineer with Python and AWS experience..."

# Pipe from stdin
cat job_description.txt | candidate-finder

# Options
candidate-finder -f jd.txt --max-candidates 15 --location "New York" --json
```

#### Python API

```python
from src.agent import find_candidates_sync

result = find_candidates_sync(
    job_description="Senior ML Engineer with PyTorch experience...",
    max_candidates=10,
    location_filter="San Francisco",
)

for match in result.candidates:
    print(f"{match.candidate.name} — {match.overall_score}/100")
    print(f"  {match.reasoning}")
```

#### Async API

```python
import asyncio
from src.agent import CandidateFinderAgent
from src.models import FindCandidatesRequest

async def main():
    agent = CandidateFinderAgent()
    request = FindCandidatesRequest(
        job_description="...",
        max_candidates=10,
    )
    result = await agent.find_candidates(request)
    return result

result = asyncio.run(main())
```

## Claude Cowork Integration

The agent integrates with Claude Cowork in three ways:

### 1. MCP Server (recommended for Claude Desktop)

Add the following to your Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "linkedin-candidate-finder": {
      "command": "python3",
      "args": ["-m", "src.cowork_server"],
      "cwd": "/path/to/this/project",
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "LINKEDIN_LI_AT": "your-cookie-here"
      }
    }
  }
```

Or use the provided `claude_cowork_config.json` as a starting point.

The MCP server exposes three tools:

| Tool | Description |
|---|---|
| `find_linkedin_candidates` | Full pipeline: parse JD, search LinkedIn, rank candidates |
| `parse_job_description` | Parse a JD into structured requirements (no search) |
| `search_linkedin_candidates` | Low-level LinkedIn search with explicit keywords/titles |

### 2. Claude Tool-Use API

Use the tool definitions directly in your own Claude API calls:

```python
import anthropic
from tools.definitions import ALL_TOOLS

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    tools=ALL_TOOLS,
    messages=[{
        "role": "user",
        "content": "Find candidates for this role: Senior Backend Engineer..."
    }],
)
```

### 3. Interactive Cowork Session

Run an interactive terminal session where Claude orchestrates the candidate search:

```bash
python3 -m src.cowork
```

This starts a conversation loop where Claude can call the candidate-finder tools autonomously.

## Testing

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run with coverage
python3 -m pytest tests/ -v --tb=short
```

## Linting

```bash
python3 -m ruff check src/ tests/ tools/
```

## Architecture

```
User
  │
  ├─ CLI (src/cli.py)
  ├─ Python API (src/agent.py)
  ├─ Cowork Session (src/cowork.py)
  │   └── Claude orchestrator with tool-use loop
  └─ MCP Server (src/cowork_server.py)
      └── Claude Desktop / Cowork integration
          │
          ▼
    CandidateFinderAgent
          │
          ├── 1. JobDescriptionParser  ──→  Claude API
          │       parse JD → JobRequirements
          │       derive → SearchCriteria
          │
          ├── 2. LinkedInCrawler
          │       ├── LinkedInAuthenticatedCrawler (Voyager API)
          │       └── GoogleXRayCrawler (fallback)
          │       → list[CandidateProfile]
          │
          └── 3. CandidateRanker  ──→  Claude API
                  score + rank → list[CandidateMatch]
```

## License

MIT
