# Railway / wkhtmltopdf fix — 2026-08-30

- Removed `wkhtmltopdf` from the Docker image because Debian Trixie no longer provides an installation candidate.
- Removed the Python `pdfkit` dependency.
- Replaced the remaining transfer PDF generator with a self-contained ReportLab implementation.
- Sales PDFs were already ReportLab-based; now production has no runtime dependency on wkhtmltopdf/pdfkit.
