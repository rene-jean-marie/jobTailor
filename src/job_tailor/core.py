"""Core library functions for job_tailor."""

import json
import re
import sys
import textwrap
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
from openai import OpenAI
from pypdf import PdfReader

SYSTEM_PROMPT = (
    "You are an expert CV/cover-letter writer for quantitative finance roles. "
    "You optimise for ATS, accuracy, and relevance. You never fabricate facts. "
    "You ask for missing information only if it is essential; otherwise you make "
    "conservative wording choices."
)


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value[:80] or "job"


def slugify_token(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")
    return value[:60] or "unknown"


def build_output_dir_name(company: str, role: str) -> str:
    company_part = slugify_token(company)
    role_part = slugify_token(role)
    return f"{company_part}_{role_part}"


def find_unique_output_dir(base_dir: Path, base_name: str) -> Path:
    """Find a unique directory name by appending incremental digits if needed."""
    output_dir = base_dir / base_name
    if not output_dir.exists():
        return output_dir

    counter = 1
    while True:
        output_dir = base_dir / f"{base_name}_{counter}"
        if not output_dir.exists():
            return output_dir
        counter += 1


def fetch_url_text(url: str, timeout: int = 20) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return extract_text_from_html(resp.text)


def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "img"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def build_job_parse_prompt(job_text: str) -> str:
    return textwrap.dedent(
        f"""
        Extract a structured job target from the following job post. Output JSON:
        {{title, company, location, responsibilities[], must_have[], nice_to_have[], tools[], keywords_ranked[]}}.
        Also output a list of 15-25 exact keyword phrases to include naturally.
        Output JSON only.

        Job post:
        {job_text}
        """
    ).strip()


def build_candidate_parse_prompt(cv_text: str) -> str:
    return textwrap.dedent(
        f"""
        Extract candidate data from the following CV into JSON:
        {{contact, summary, skills{{programming[], quant[], data[], tools[]}}, experience[{{company, title, dates, bullets[]}}], education[], leadership[]}}.
        Do not rewrite; only structure. Output JSON only.

        CV:
        {cv_text}
        """
    ).strip()


def build_mapping_prompt(job_json: str, candidate_json: str) -> str:
    return textwrap.dedent(
        f"""
        Using job JSON and candidate JSON, create a requirement-to-evidence matrix. For each must-have and top responsibilities:
        best matching candidate evidence
        suggested CV phrasing
        confidence (High/Med/Low)
        gaps (if any) and safe mitigation wording.
        Output Markdown table.

        Job JSON:
        {job_json}

        Candidate JSON:
        {candidate_json}
        """
    ).strip()


def build_cv_prompt(job_json: str, candidate_json: str, mapping_md: str) -> str:
    return textwrap.dedent(
        f"""
        Create an ATS-optimised CV for the target role. Maximise keyword alignment and relevance while remaining truthful and specific. Preserve a professional UK tone. Output final documents as plain text sections ready for PDF layout.

        Hard constraints:
        - Do not invent experience, employers, dates, tools, degrees, or achievements.
        - Prefer quantified impact; if metrics are missing, write outcome-focused bullets without numbers.
        - Optimise for ATS parsing: standard headings, no tables, no icons, no columns, no text boxes, no images.
        - Use UK English.
        - CV length: 1 page (strict).
        - Cover letter: 250-350 words.

        Content strategy:
        - Create a Requirements-to-Evidence matrix: for each job requirement, cite the best matching CV evidence and propose phrasing.
        - Rewrite experience bullets to emphasise: modelling, data integrity, automation, code quality, performance, collaboration.
        - Add a "Key Skills" section that mirrors the job description's vocabulary without keyword stuffing.
        - Tailor the summary to the role's domain (systematic trading / quant research / data).
        - Include only the most relevant coursework; remove weak or irrelevant items.

        Use this mapping:
        {mapping_md}

        Job JSON:
        {job_json}

        Candidate JSON:
        {candidate_json}

        Output format requirements:
        Return the Final CV only.
        """
    ).strip()


def build_ats_audit_prompt(job_json: str, cv_text: str) -> str:
    return textwrap.dedent(
        f"""
        Audit the CV for ATS parseability and keyword alignment. Output:
        - missing critical keywords (only those that are truthful to add),
        - formatting risks,
        - proposed edits,
        - revised CV.

        Output JSON only in this shape:
        {{
          "missing_keywords": [],
          "formatting_risks": [],
          "proposed_edits": [],
          "revised_cv": ""
        }}

        Job JSON:
        {job_json}

        CV:
        {cv_text}
        """
    ).strip()


def build_cover_letter_prompt(
    job_json: str, candidate_json: str, mapping_md: str
) -> str:
    return textwrap.dedent(
        f"""
        Write a 250-350 word cover letter tailored to the job. Use the top 6 requirements and corresponding evidence. Keep it specific, professional UK tone, and avoid generic claims.

        Job JSON:
        {job_json}

        Candidate JSON:
        {candidate_json}

        Mapping:
        {mapping_md}
        """
    ).strip()


def generate_with_openai(model: str, prompt: str, temperature: Optional[float]) -> str:
    client = OpenAI()
    if temperature is not None and (temperature < 0 or temperature > 2):
        raise ValueError(f"temperature must be between 0 and 2, got {temperature}")

    request_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }

    if temperature is not None and not model.startswith("gpt-5"):
        request_kwargs["temperature"] = temperature
    try:
        resp = client.chat.completions.create(**request_kwargs)
    except Exception as e:
        msg = str(e)
        if "temperature" in msg and "Only the default (1) value is supported" in msg:
            request_kwargs.pop("temperature", None)
            try:
                resp = client.chat.completions.create(**request_kwargs)
            except Exception as retry_err:
                raise RuntimeError(f"OpenAI API call failed: {retry_err}") from retry_err
        else:
            raise RuntimeError(f"OpenAI API call failed: {e}") from e

    # Safely extract textual content; handle potential None content
    content = ""
    choices = getattr(resp, "choices", []) or []
    for choice in choices:
        msg = getattr(choice, "message", None)
        if not msg:
            continue
        c = getattr(msg, "content", None)
        if isinstance(c, str) and c.strip():
            content = c
            break

    if not content and choices:
        # Fallback: attempt to coerce first choice content to string if present
        c0 = getattr(choices[0].message, "content", "")
        content = c0 if isinstance(c0, str) else ""

    return content.strip()


def generate_dry_run(cv_text: str, job_text: str) -> str:
    preview_cv = "\n".join(cv_text.splitlines()[:40]).strip()
    preview_job = "\n".join(job_text.splitlines()[:40]).strip()
    return textwrap.dedent(
        f"""
        # Dry Run Output

        This is a dry run output. No API call was made.

        ## CV preview
        {preview_cv}

        ## Job posting preview
        {preview_job}
        """
    ).strip()


def parse_json_response(raw: str) -> dict:
    text = raw.strip()

    if "```" in text:
        parts = text.split("```")
        for i in range(1, len(parts), 2):
            block = parts[i].strip()
            if block.lower().startswith("json"):
                block = block[4:].strip()
            try:
                parsed = json.loads(block)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

    start_candidates = [pos for pos in (text.find("{"), text.find("[")) if pos != -1]
    if not start_candidates:
        raise ValueError("Invalid JSON response: no JSON object/array found")

    start = min(start_candidates)
    decoder = json.JSONDecoder()
    try:
        parsed, _ = decoder.raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON response: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Invalid JSON response: expected a JSON object")
    return parsed


def markdown_to_pdf(markdown_text: str, output_path: Path) -> None:
    pdf = FPDF(unit="pt", format="A4")
    pdf.set_auto_page_break(auto=True, margin=54)
    pdf.add_page()

    def normalize_text(text: str) -> str:
        replacements = {
            "–": "-",
            "—": "--",
            "•": "-",
            "→": "->",
            "←": "<-",
            "“": '"',
            "”": '"',
            "‘": "'",
            "’": "'",
            "‑": "-",
            "\u00a0": " ",
        }
        for src, dst in replacements.items():
            text = text.replace(src, dst)
        return text

    def break_long_words(text: str, max_len: int = 60) -> str:
        parts = []
        for token in text.split(" "):
            if len(token) <= max_len:
                parts.append(token)
                continue
            chunks = [token[i : i + max_len] for i in range(0, len(token), max_len)]
            parts.append(" ".join(chunks))
        return " ".join(parts)

    def write_line(text: str, size: int, bold: bool = False, indent: int = 0) -> None:
        # Use enums when available to satisfy type-checkers; fall back to strings for older fpdf2 versions
        try:
            from fpdf.enums import WrapMode, XPos, YPos  # type: ignore

            new_x_val = XPos.LMARGIN
            new_y_val = YPos.NEXT
            wrap_mode_val = WrapMode.CHAR
        except Exception:
            new_x_val = "LMARGIN"
            new_y_val = "NEXT"
            wrap_mode_val = "CHAR"

        pdf.set_font("Helvetica", style="B" if bold else "", size=size)
        if indent:
            pdf.set_x(pdf.l_margin + indent)
        safe_text = normalize_text(break_long_words(text))
        pdf.multi_cell(
            0,
            size + 6,
            safe_text,
            new_x=new_x_val,
            new_y=new_y_val,
            wrapmode=wrap_mode_val,
        )

    lines = markdown_text.splitlines()
    for line in lines:
        if not line.strip():
            pdf.ln(6)
            continue
        if line.startswith("# "):
            write_line(line[2:].strip(), size=18, bold=True)
        elif line.startswith("## "):
            write_line(line[3:].strip(), size=14, bold=True)
        elif line.startswith("### "):
            write_line(line[4:].strip(), size=12, bold=True)
        elif line.startswith("- "):
            write_line(f"- {line[2:].strip()}", size=11, indent=10)
        else:
            write_line(line.strip(), size=11)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))


def process_job(
    cv_text: str,
    job_text: str,
    out_dir: Path,
    slug: str,
    model: str,
    temperature: float,
    dry_run: bool,
    make_pdf: bool,
    verbose: bool,
    debug_artifacts: bool,
    include_cover_letter: bool,
) -> List[Path]:
    def log(step: str) -> None:
        if verbose:
            print(f"[job:{slug}] {step}")

    output_dir = out_dir
    base_name = ""
    if dry_run:
        log("Generate output (dry run)")
        output_md = generate_dry_run(cv_text, job_text)
        base_name = build_output_dir_name("unknown-company", "unknown-role")
    else:
        log("Parse candidate CV")
        candidate_json_raw = generate_with_openai(
            model, build_candidate_parse_prompt(cv_text), temperature=0.0
        )
        candidate_json = parse_json_response(candidate_json_raw)
        candidate_json_text = json.dumps(candidate_json, indent=2)

        log("Parse job description")
        job_json_raw = generate_with_openai(
            model, build_job_parse_prompt(job_text), temperature=0.0
        )
        job_json = parse_json_response(job_json_raw)
        job_json_text = json.dumps(job_json, indent=2)

        log("Build mapping table")
        mapping_md = generate_with_openai(
            model, build_mapping_prompt(job_json_text, candidate_json_text), temperature
        )

        company_name = job_json.get("company") or "unknown-company"
        role_name = job_json.get("title") or "unknown-role"
        base_name = build_output_dir_name(str(company_name), str(role_name))
        output_dir = find_unique_output_dir(out_dir, base_name)
        base_name = output_dir.name

        log("Draft CV")
        cv_draft = generate_with_openai(
            model,
            build_cv_prompt(job_json_text, candidate_json_text, mapping_md),
            temperature,
        )

        log("ATS audit")
        ats_audit_raw = generate_with_openai(
            model, build_ats_audit_prompt(job_json_text, cv_draft), temperature=0.0
        )
        ats_audit = parse_json_response(ats_audit_raw)
        final_cv = ats_audit.get("revised_cv", cv_draft)

        cover_letter = ""
        if include_cover_letter:
            log("Draft cover letter")
            cover_letter = generate_with_openai(
                model,
                build_cover_letter_prompt(job_json_text, candidate_json_text, mapping_md),
                temperature,
            )

        output_md = ""

    log("Write outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    cv_md_path = output_dir / f"{base_name}_cv.md"
    cover_md_path = output_dir / f"{base_name}_cover_letter.md"
    cv_pdf_path = output_dir / f"{base_name}_cv.pdf"
    cover_pdf_path = output_dir / f"{base_name}_cover_letter.pdf"

    if output_md:
        cv_md_path.write_text(output_md, encoding="utf-8")
        created_paths = [cv_md_path]
        if include_cover_letter:
            cover_md_path.write_text(output_md, encoding="utf-8")
            created_paths.append(cover_md_path)
    else:
        cv_md_path.write_text(final_cv, encoding="utf-8")
        created_paths = [cv_md_path]
        if include_cover_letter:
            cover_md_path.write_text(cover_letter, encoding="utf-8")
            created_paths.append(cover_md_path)

        if debug_artifacts:
            debug_paths = [
                output_dir / f"{base_name}_candidate.json",
                output_dir / f"{base_name}_job.json",
                output_dir / f"{base_name}_mapping.md",
                output_dir / f"{base_name}_cv_draft.md",
                output_dir / f"{base_name}_ats_audit.json",
            ]
            debug_paths[0].write_text(candidate_json_text, encoding="utf-8")
            debug_paths[1].write_text(job_json_text, encoding="utf-8")
            debug_paths[2].write_text(mapping_md, encoding="utf-8")
            debug_paths[3].write_text(cv_draft, encoding="utf-8")
            debug_paths[4].write_text(
                json.dumps(ats_audit, indent=2), encoding="utf-8"
            )
            created_paths.extend(debug_paths)

    if make_pdf:
        log("Render PDFs")
        markdown_to_pdf(cv_md_path.read_text(encoding="utf-8"), cv_pdf_path)
        created_paths.append(cv_pdf_path)
        if include_cover_letter:
            markdown_to_pdf(cover_md_path.read_text(encoding="utf-8"), cover_pdf_path)
            created_paths.append(cover_pdf_path)

    return created_paths


def load_job_texts(
    urls: Iterable[str], job_text_file: Path | None
) -> List[Tuple[str, str]]:
    if job_text_file:
        text = job_text_file.read_text(encoding="utf-8")
        return [("job", text)]

    jobs = []
    for url in urls:
        cleaned_url = "".join(url.split())
        if cleaned_url != url:
            print(
                "Warning: job URL contained whitespace; cleaned it before fetching.",
                file=sys.stderr,
            )
            url = cleaned_url
        text = fetch_url_text(url)
        jobs.append((url, text))
    return jobs


def load_cv_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        pages = [(page.extract_text() or "") for page in reader.pages]
        return "\n".join(pages).strip()
    return path.read_text(encoding="utf-8")


def tailor_documents(
    cv_file: str | Path,
    job_urls: Optional[Iterable[str]] = None,
    job_text_file: str | Path | None = None,
    out_dir: str | Path = "outputs",
    model: str = "gpt-5-mini",
    temperature: float = 0.2,
    dry_run: bool = False,
    make_pdf: bool = True,
    verbose: bool = True,
    debug_artifacts: bool = True,
    include_cover_letter: bool = True,
) -> List[Path]:
    """Generate tailored CV and cover letter outputs from file/URL inputs."""
    if not job_urls and not job_text_file:
        raise ValueError("Provide job_urls or job_text_file")

    cv_text = load_cv_text(Path(cv_file))
    out_dir_path = Path(out_dir)
    job_text_path = Path(job_text_file) if job_text_file else None

    jobs = load_job_texts(job_urls or [], job_text_path)

    created_paths: List[Path] = []
    for source, job_text in jobs:
        slug = slugify(source)
        created_paths.extend(
            process_job(
                cv_text=cv_text,
                job_text=job_text,
                out_dir=out_dir_path,
                slug=slug,
                model=model,
                temperature=temperature,
                dry_run=dry_run,
                make_pdf=make_pdf,
                verbose=verbose,
                debug_artifacts=debug_artifacts,
                include_cover_letter=include_cover_letter,
            )
        )

    return created_paths


def create_cv_only(
    cv_file: str | Path,
    job_urls: Optional[Iterable[str]] = None,
    job_text_file: str | Path | None = None,
    out_dir: str | Path = "outputs",
    model: str = "gpt-5-mini",
    temperature: float = 0.2,
    dry_run: bool = False,
    make_pdf: bool = True,
    verbose: bool = True,
    debug_artifacts: bool = True,
) -> List[Path]:
    """Generate only the tailored CV outputs from file/URL inputs."""
    return tailor_documents(
        cv_file=cv_file,
        job_urls=job_urls,
        job_text_file=job_text_file,
        out_dir=out_dir,
        model=model,
        temperature=temperature,
        dry_run=dry_run,
        make_pdf=make_pdf,
        verbose=verbose,
        debug_artifacts=debug_artifacts,
        include_cover_letter=False,
    )
