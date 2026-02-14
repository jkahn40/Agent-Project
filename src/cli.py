"""Command-line interface for the LinkedIn Candidate Finder agent."""

from __future__ import annotations

import argparse
import logging
import sys

from src.agent import find_candidates_sync


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="candidate-finder",
        description="Analyse a job description and find matching LinkedIn candidates.",
    )
    parser.add_argument(
        "job_description",
        nargs="?",
        help="Job description text (or pass via --file / stdin).",
    )
    parser.add_argument(
        "-f",
        "--file",
        help="Read job description from a file.",
    )
    parser.add_argument(
        "-n",
        "--max-candidates",
        type=int,
        default=10,
        help="Maximum number of candidates to return (default: 10).",
    )
    parser.add_argument(
        "-l",
        "--location",
        default=None,
        help="Additional location filter.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output raw JSON instead of a human-readable report.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose / debug logging.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    # Read JD text
    if args.file:
        with open(args.file) as fh:
            jd_text = fh.read()
    elif args.job_description:
        jd_text = args.job_description
    elif not sys.stdin.isatty():
        jd_text = sys.stdin.read()
    else:
        parser.error(
            "Provide a job description as an argument, via --file, or pipe to stdin."
        )

    result = find_candidates_sync(
        job_description=jd_text,
        max_candidates=args.max_candidates,
        location_filter=args.location,
    )

    if args.output_json:
        print(result.model_dump_json(indent=2))
    else:
        _print_report(result)


def _print_report(result) -> None:  # noqa: ANN001
    """Pretty-print the results to the terminal."""
    req = result.job_requirements
    print("=" * 72)
    print(f"  Job: {req.title}  ({req.seniority.value})")
    print(f"  Location: {req.location or 'Not specified'}")
    print(f"  Required skills: {', '.join(req.required_skills)}")
    if req.preferred_skills:
        print(f"  Preferred skills: {', '.join(req.preferred_skills)}")
    print(f"  Summary: {req.summary}")
    print("=" * 72)
    print()

    print(f"Scanned {result.total_profiles_scanned} profiles.  "
          f"Showing top {len(result.candidates)} matches.\n")

    for i, match in enumerate(result.candidates, 1):
        c = match.candidate
        print(f"  #{i}  {c.name}")
        print(f"      Score: {match.overall_score:.0f}/100  "
              f"(Skills: {match.skill_match_score:.0f}, "
              f"Experience: {match.experience_match_score:.0f})")
        if c.headline:
            print(f"      Headline: {c.headline}")
        if c.location:
            print(f"      Location: {c.location}")
        print(f"      Profile: {c.profile_url}")
        print(f"      Reasoning: {match.reasoning}")
        if match.strengths:
            print(f"      Strengths: {', '.join(match.strengths)}")
        if match.gaps:
            print(f"      Gaps: {', '.join(match.gaps)}")
        print()


if __name__ == "__main__":
    main()
