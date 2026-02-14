"""LinkedIn search & profile crawling module.

This module provides two search strategies:

1. **Authenticated LinkedIn search** — uses the ``li_at`` session cookie to
   query LinkedIn's Voyager API (the same API the browser SPA uses).  This
   gives accurate, paginated results.

2. **Google X-Ray search** — falls back to Google ``site:linkedin.com/in``
   queries, which works without authentication but returns fewer results.

The crawler is deliberately *polite*: it adds random delays, respects
rate-limits, and never attempts to bypass LinkedIn's anti-scraping protections.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import urllib.parse
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from src.models import CandidateProfile, Education, Experience, SearchCriteria

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LINKEDIN_SEARCH_URL = "https://www.linkedin.com/voyager/api/search/dash/clusters"
LINKEDIN_PROFILE_URL = "https://www.linkedin.com/voyager/api/identity/profiles/{public_id}"
LINKEDIN_PROFILE_VIEW = "https://www.linkedin.com/in/{public_id}"
GOOGLE_SEARCH_URL = "https://www.google.com/search"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

VOYAGER_HEADERS = {
    **DEFAULT_HEADERS,
    "Accept": "application/vnd.linkedin.normalized+json+2.1",
    "x-li-lang": "en_US",
    "x-restli-protocol-version": "2.0.0",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _polite_delay(lo: float = 1.0, hi: float = 3.0) -> None:
    """Sleep a random interval to be respectful to servers."""
    await asyncio.sleep(random.uniform(lo, hi))


def _build_search_keywords(criteria: SearchCriteria) -> list[str]:
    """Build a set of LinkedIn/Google search query strings from criteria."""
    queries: list[str] = []

    # Primary query: combine titles with keywords
    for title in criteria.titles[:3]:
        kw = " ".join(criteria.keywords[:4])
        queries.append(f"{title} {kw}")

    # Secondary query: keywords + location
    if criteria.locations:
        kw = " ".join(criteria.keywords[:3])
        loc = criteria.locations[0]
        queries.append(f"{kw} {loc}")

    return queries


# ---------------------------------------------------------------------------
# LinkedIn Voyager API search (authenticated)
# ---------------------------------------------------------------------------


class LinkedInAuthenticatedCrawler:
    """Search LinkedIn using the Voyager API with a session cookie."""

    def __init__(self, li_at_cookie: str):
        self.cookies = {"li_at": li_at_cookie}
        self._csrf_token: Optional[str] = None

    async def _get_csrf_token(self, client: httpx.AsyncClient) -> str:
        """Fetch CSRF token from LinkedIn by loading a page."""
        if self._csrf_token:
            return self._csrf_token
        resp = await client.get(
            "https://www.linkedin.com/feed/",
            cookies=self.cookies,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        )
        # The CSRF token is in the JSESSIONID cookie or the page meta
        jsessionid = resp.cookies.get("JSESSIONID", "")
        self._csrf_token = jsessionid.strip('"')
        return self._csrf_token

    async def search_people(
        self,
        criteria: SearchCriteria,
        max_results: int = 25,
    ) -> list[CandidateProfile]:
        """Search LinkedIn People via the Voyager API."""
        candidates: list[CandidateProfile] = []

        async with httpx.AsyncClient(timeout=30) as client:
            csrf = await self._get_csrf_token(client)
            headers = {**VOYAGER_HEADERS, "csrf-token": csrf}

            queries = _build_search_keywords(criteria)
            for query in queries:
                if len(candidates) >= max_results:
                    break

                logger.info("LinkedIn Voyager search: %r", query)
                params = {
                    "decorationId": (
                        "com.linkedin.voyager.dash.deco.search"
                        ".SearchClusterCollection-175"
                    ),
                    "origin": "GLOBAL_SEARCH_HEADER",
                    "q": "all",
                    "query": f"(keywords:{urllib.parse.quote(query)},"
                    "filters:List((key:resultType,value:List(PEOPLE))))",
                    "start": 0,
                    "count": min(25, max_results - len(candidates)),
                }

                try:
                    resp = await client.get(
                        LINKEDIN_SEARCH_URL,
                        params=params,
                        headers=headers,
                        cookies=self.cookies,
                        follow_redirects=True,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        new_candidates = self._parse_search_results(data)
                        candidates.extend(new_candidates)
                        logger.info("  → found %d profiles", len(new_candidates))
                    elif resp.status_code == 429:
                        logger.warning("Rate-limited by LinkedIn, pausing …")
                        await asyncio.sleep(60)
                    else:
                        logger.warning(
                            "LinkedIn search returned %d", resp.status_code
                        )
                except httpx.HTTPError as exc:
                    logger.error("LinkedIn search failed: %s", exc)

                await _polite_delay(2.0, 5.0)

        # Deduplicate by profile URL
        seen: set[str] = set()
        unique: list[CandidateProfile] = []
        for c in candidates:
            if c.profile_url not in seen:
                seen.add(c.profile_url)
                unique.append(c)
        return unique[:max_results]

    async def enrich_profile(
        self, public_id: str, client: httpx.AsyncClient, headers: dict
    ) -> Optional[CandidateProfile]:
        """Fetch detailed profile data for a single public identifier."""
        url = LINKEDIN_PROFILE_URL.format(public_id=public_id)
        try:
            resp = await client.get(
                url,
                headers=headers,
                cookies=self.cookies,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                return self._parse_full_profile(resp.json(), public_id)
        except httpx.HTTPError as exc:
            logger.error("Profile fetch for %s failed: %s", public_id, exc)
        return None

    # ----- parsers -----

    @staticmethod
    def _parse_search_results(data: dict) -> list[CandidateProfile]:
        """Extract candidate profiles from Voyager search JSON."""
        candidates: list[CandidateProfile] = []
        included = data.get("included", [])
        for item in included:
            # People results have a specific $type
            entity_type = item.get("$type", "")
            if "MiniProfile" in entity_type or "Profile" in entity_type:
                public_id = item.get("publicIdentifier") or item.get("public_id", "")
                if not public_id:
                    continue
                name_parts = [
                    item.get("firstName", ""),
                    item.get("lastName", ""),
                ]
                name = " ".join(p for p in name_parts if p).strip()
                if not name:
                    continue
                candidates.append(
                    CandidateProfile(
                        name=name,
                        headline=item.get("occupation") or item.get("headline"),
                        location=item.get("locationName"),
                        profile_url=LINKEDIN_PROFILE_VIEW.format(public_id=public_id),
                        current_title=item.get("occupation"),
                    )
                )
        return candidates

    @staticmethod
    def _parse_full_profile(data: dict, public_id: str) -> CandidateProfile:
        """Parse a full Voyager profile response."""
        included = data.get("included", [])
        profile_data: dict = {}
        experiences: list[Experience] = []
        educations: list[Education] = []
        skills: list[str] = []

        for item in included:
            t = item.get("$type", "")
            if "Profile" in t and item.get("publicIdentifier") == public_id:
                profile_data = item
            elif "Position" in t:
                experiences.append(
                    Experience(
                        title=item.get("title", "Unknown"),
                        company=item.get("companyName", "Unknown"),
                        location=item.get("locationName"),
                        description=item.get("description"),
                    )
                )
            elif "Education" in t:
                educations.append(
                    Education(
                        school=item.get("schoolName", "Unknown"),
                        degree=item.get("degreeName"),
                        field_of_study=item.get("fieldOfStudy"),
                    )
                )
            elif "Skill" in t:
                skill_name = item.get("name")
                if skill_name:
                    skills.append(skill_name)

        name = " ".join(
            filter(
                None,
                [profile_data.get("firstName"), profile_data.get("lastName")],
            )
        ) or "Unknown"

        return CandidateProfile(
            name=name,
            headline=profile_data.get("headline"),
            location=profile_data.get("locationName"),
            profile_url=LINKEDIN_PROFILE_VIEW.format(public_id=public_id),
            summary=profile_data.get("summary"),
            current_title=profile_data.get("headline"),
            skills=skills,
            experience=experiences,
            education=educations,
        )


# ---------------------------------------------------------------------------
# Google X-Ray search (unauthenticated fallback)
# ---------------------------------------------------------------------------


class GoogleXRayCrawler:
    """Find LinkedIn profiles via Google ``site:linkedin.com/in`` queries."""

    async def search_people(
        self,
        criteria: SearchCriteria,
        max_results: int = 25,
    ) -> list[CandidateProfile]:
        candidates: list[CandidateProfile] = []
        queries = _build_search_keywords(criteria)

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for query in queries:
                if len(candidates) >= max_results:
                    break

                google_query = f'site:linkedin.com/in "{query}"'
                logger.info("Google X-Ray search: %r", google_query)

                try:
                    resp = await client.get(
                        GOOGLE_SEARCH_URL,
                        params={"q": google_query, "num": 10},
                        headers=DEFAULT_HEADERS,
                    )
                    if resp.status_code == 200:
                        new = self._parse_google_results(resp.text)
                        candidates.extend(new)
                        logger.info("  → found %d profiles", len(new))
                    elif resp.status_code == 429:
                        logger.warning("Rate-limited by Google, pausing …")
                        await asyncio.sleep(30)
                    else:
                        logger.warning("Google returned %d", resp.status_code)
                except httpx.HTTPError as exc:
                    logger.error("Google search failed: %s", exc)

                await _polite_delay(3.0, 7.0)

        # Deduplicate
        seen: set[str] = set()
        unique: list[CandidateProfile] = []
        for c in candidates:
            if c.profile_url not in seen:
                seen.add(c.profile_url)
                unique.append(c)
        return unique[:max_results]

    @staticmethod
    def _parse_google_results(html: str) -> list[CandidateProfile]:
        """Parse Google SERP HTML to extract LinkedIn profile links."""
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[CandidateProfile] = []

        for a_tag in soup.select("a[href]"):
            href = a_tag.get("href", "")
            # Google wraps links in /url?q=… redirects
            if "/url?q=" in href:
                match = re.search(r"/url\?q=(https?://[^&]+)", href)
                if match:
                    href = urllib.parse.unquote(match.group(1))

            if "linkedin.com/in/" not in href:
                continue

            # Normalise URL
            parsed = urllib.parse.urlparse(href)
            path = parsed.path.rstrip("/")
            profile_url = f"https://www.linkedin.com{path}"
            public_id = path.split("/in/")[-1].split("/")[0] if "/in/" in path else ""
            if not public_id:
                continue

            # Try to extract name / headline from the search snippet
            parent = a_tag.find_parent("div")
            text_block = parent.get_text(" ", strip=True) if parent else ""
            # Google snippets often have "FirstName LastName - Title - LinkedIn"
            name = public_id.replace("-", " ").title()
            headline = None
            if " - " in text_block:
                parts = text_block.split(" - ")
                if len(parts) >= 2:
                    name = parts[0].strip() or name
                    headline = parts[1].strip()

            candidates.append(
                CandidateProfile(
                    name=name,
                    headline=headline,
                    profile_url=profile_url,
                    current_title=headline,
                )
            )

        return candidates


# ---------------------------------------------------------------------------
# Unified crawler interface
# ---------------------------------------------------------------------------


class LinkedInCrawler:
    """Unified crawler that tries authenticated access first, then falls back
    to Google X-Ray search."""

    def __init__(self, li_at_cookie: Optional[str] = None):
        self._authenticated: Optional[LinkedInAuthenticatedCrawler] = None
        self._google = GoogleXRayCrawler()

        if li_at_cookie:
            self._authenticated = LinkedInAuthenticatedCrawler(li_at_cookie)
            logger.info("LinkedIn session cookie provided — using authenticated search")
        else:
            logger.info("No LinkedIn cookie — will fall back to Google X-Ray search")

    async def search(
        self,
        criteria: SearchCriteria,
        max_results: int = 25,
    ) -> tuple[list[CandidateProfile], list[str]]:
        """Search for candidates.  Returns (profiles, queries_used)."""
        queries_used = _build_search_keywords(criteria)
        profiles: list[CandidateProfile] = []

        if self._authenticated:
            try:
                profiles = await self._authenticated.search_people(
                    criteria, max_results=max_results
                )
                if profiles:
                    return profiles, queries_used
                logger.warning(
                    "Authenticated search returned 0 results, falling back to Google"
                )
            except Exception as exc:
                logger.error(
                    "Authenticated search failed (%s), falling back to Google", exc
                )

        profiles = await self._google.search_people(
            criteria, max_results=max_results
        )
        return profiles, queries_used
