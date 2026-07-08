# Security Policy

## Reporting a vulnerability

Please do not report security vulnerabilities through public GitHub issues.

Instead, use [GitHub private vulnerability reporting](https://github.com/kynetyk-ai/skillspar/security/advisories/new)
to submit a report, or email hello@kynetyk.ai with the details.

Please include:

- A description of the issue and its potential impact
- Steps to reproduce
- Any relevant configuration (OS, Python version, skillspar version)

We will acknowledge reports within 5 business days.

## Scope notes

Skillspar executes eval suites that send prompts to model APIs and runs a
Claude Code skill package. Reports about prompt-injection vectors in the
`/skillspar:evaluate` skill, credential handling (`.env`, API keys), or unsafe
handling of untrusted `.eval.yaml` / SKILL.md content are in scope.
