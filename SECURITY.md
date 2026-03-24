# Security Policy

## Medical Data

This project processes anonymized radiology reports. Even anonymized medical text can carry residual re-identification risk.

- **Never** commit patient data, DICOM files, or radiology reports to this repository
- **Never** commit API keys, tokens, or credentials (use `.env` files, which are gitignored)
- All extraction outputs go to `output/` (gitignored) and must not be shared publicly
- When using external LLM APIs, ensure your organization has appropriate data processing agreements

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it privately via GitHub Security Advisories rather than opening a public issue.

## Regulatory Notice

This software generates **silver-standard reference labels** from radiology reports using LLM extraction. These labels are NOT validated for clinical use. They require human adjudication before any clinical application. This software is not a medical device and has not been cleared by any regulatory body (ANVISA, FDA, CE).
