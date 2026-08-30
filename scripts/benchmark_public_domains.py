#!/usr/bin/env python3
"""Repository entry point for non-fall public-data engineering checks."""

from kangshield.validation.public_domains import main


if __name__ == "__main__":
    raise SystemExit(main())
