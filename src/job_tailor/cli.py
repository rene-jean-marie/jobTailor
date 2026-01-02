#!/usr/bin/env python3
"""Command-line interface for job_tailor."""

import argparse

from dotenv import load_dotenv

from .core import tailor_documents


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Tailor a CV and cover letter for job postings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\\n"
            "  python -m job_tailor --cv-file /path/to/base_cv.md --job-url https://... --job-url https://...\\n"
            "  python -m job_tailor --cv-file /path/to/base_cv.md --job-text-file /path/to/job.txt\\n"
            "  python -m job_tailor --cv-file /path/to/base_cv.md --job-url https://... --cv-only\\n"
        ),
    )
    parser.add_argument(
        "--cv-file",
        default="/Users/renejean-marie/code/python/job-tailor/Rene_Jean-Marie_CV.pdf",
        help="Path to base CV (Markdown/text)",
    )
    parser.add_argument(
        "--job-url",
        action="append",
        default=["https://www.linkedin.com/jobs/view/4348942395"],
        help="Job posting URL (repeatable)",
    )
    parser.add_argument(
        "--job-text-file",
        help="Optional job posting text file (skip URL fetch)",
    )
    parser.add_argument(
        "--out-dir",
        default="outputs",
        help="Output directory for generated files",
    )
    parser.add_argument("--model", default="gpt-5-mini", help="OpenAI model")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip OpenAI calls and generate stub outputs",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Skip PDF generation (write Markdown outputs only)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output (only print created files)",
    )
    parser.add_argument(
        "--no-debug-artifacts",
        action="store_true",
        help="Skip writing intermediate JSON and drafts",
    )
    parser.add_argument(
        "--cv-only",
        action="store_true",
        help="Generate only the CV (skip cover letter outputs)",
    )

    args = parser.parse_args()

    created_paths = tailor_documents(
        cv_file=args.cv_file,
        job_urls=args.job_url or [],
        job_text_file=args.job_text_file,
        out_dir=args.out_dir,
        model=args.model,
        temperature=args.temperature,
        dry_run=args.dry_run,
        make_pdf=not args.no_pdf,
        verbose=not args.quiet,
        debug_artifacts=not args.no_debug_artifacts,
        include_cover_letter=not args.cv_only,
    )

    for path in created_paths:
        print(f"Created: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
