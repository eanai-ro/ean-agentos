# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| latest  | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in EAN AgentOS, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, email us at: **ean@eanai.ro**

Include:
- Description of the vulnerability
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

## Response Timeline

- **Acknowledgment**: within 48 hours
- **Initial assessment**: within 1 week
- **Fix release**: depends on severity (critical: ASAP, high: 1 week, medium: 2 weeks)

## Scope

This policy applies to:
- All Python scripts in `scripts/`
- The MCP server (`mcp_server/`)
- The web dashboard (`web/`)
- The install script (`install.sh`)
- Hook scripts (`scripts/hooks/`)

## Security Features

EAN AgentOS includes built-in security measures:
- **Secret scrubbing**: 15+ regex patterns detect and scrub API keys, tokens, passwords before storage
- **Guard system**: blocks storage of detected secrets
- **Quarantine**: suspicious content is quarantined, not stored
- **Audit log**: all scrubbing/quarantine actions are logged
- **Local-only**: all data stays on your machine (SQLite), no external services

## Known Limitations

- The web dashboard (`web_server.py`) has no authentication — it's designed for localhost use only
- If exposed to a network, add authentication or use a reverse proxy
- SQLite concurrent write access relies on WAL mode + busy_timeout
