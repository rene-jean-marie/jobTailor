# Job Tailor

Generate a multi-pass ATS-focused CV and cover letter pack from job postings.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set your OpenAI key:

```bash
export OPENAI_API_KEY="..."
```

## Usage

From the project folder:

```bash
python tailor_cv.py \
  --cv-file /path/to/base_cv.md \
  --job-url "https://www.linkedin.com/jobs/view/123..." \
  --job-url "https://www.efinancialcareers.com/jobs-..." \
  --out-dir outputs
```

Outputs (per job, files are prefixed with `<company>_<role>_<date_created>`):
- `outputs/<company>_<role>_<date_created>_cv.md`
- `outputs/<company>_<role>_<date_created>_cover_letter.md`
- `outputs/<company>_<role>_<date_created>_cv.pdf` (unless `--no-pdf`)
- `outputs/<company>_<role>_<date_created>_cover_letter.pdf` (unless `--no-pdf`)

## Notes

- LinkedIn and some job boards may block automated fetching. If a URL fetch fails, save the job description to a text file and use:

```bash
python tailor_cv.py \
  --cv-file /path/to/base_cv.md \
  --job-text-file /path/to/job.txt \
  --out-dir outputs

# Skip PDF generation (Markdown only)
python tailor_cv.py \
  --cv-file /path/to/base_cv.md \
  --job-url "https://www.linkedin.com/jobs/view/123..." \
  --out-dir outputs \
  --no-pdf

# Quiet mode (suppress progress logs)
python tailor_cv.py \
  --cv-file /path/to/base_cv.md \
  --job-url "https://www.linkedin.com/jobs/view/123..." \
  --out-dir outputs \
  --quiet

# Debug artifacts are saved by default.
# To skip writing intermediate JSON and drafts:
python tailor_cv.py \
  --cv-file /path/to/base_cv.md \
  --job-url "https://www.linkedin.com/jobs/view/123..." \
  --out-dir outputs \
  --no-debug-artifacts

# Dry run (no API calls)
python tailor_cv.py \
  --cv-file /path/to/base_cv.md \
  --job-url "https://www.linkedin.com/jobs/view/123..." \
  --out-dir outputs \
  --dry-run
```

- The generator does not fabricate details; it only reorders and rephrases content from your base CV.
