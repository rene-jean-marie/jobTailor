"""Module entrypoint for `python -m job_tailor`."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
