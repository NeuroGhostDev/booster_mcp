# Security Policy

## Supported Versions

Security fixes are applied to the latest `4.1.x` release line.

| Version | Supported |
| --- | --- |
| 4.1.x | Yes |
| 4.0.x and older | No |

Upgrade to the latest release before reporting an issue that may already be
fixed.

## Reporting a Vulnerability

Please do not disclose security vulnerabilities in a public GitHub issue,
discussion, pull request, or chat message.

Use GitHub Private Vulnerability Reporting:

<https://github.com/NeuroGhostDev/booster_mcp/security/advisories/new>

Include, when available:

- affected Booster version and commit;
- operating system, Python version, and installation method;
- a minimal reproduction or safe proof of concept;
- the affected command, endpoint, or integration;
- security impact and required permissions;
- sanitized logs, traces, and configuration details.

Do not include repository source code, credentials, API keys, access tokens,
private URLs, model weights, or other sensitive data unless it is strictly
required to reproduce the issue. Replace sensitive values with explicit
placeholders.

Maintainers will validate the report, determine affected versions, and
coordinate a fix, release, and disclosure timeline with the reporter.

## Security Model

Booster is a local developer tool. The default trust boundary is the user and
the machine running Booster. The core runtime can read the repositories,
artifacts, Git metadata, and configuration that the user explicitly binds to
it.

The read-only Observatory follows these boundaries:

- browser requests select repositories through logical IDs, not arbitrary
  filesystem paths;
- repository-relative paths are resolved and checked against an allowlist;
- Code City files are served only from the selected repository artifact area;
- public demo mode loads prepared JSON+FAISS, diagnostics, history, and
  snapshot data without indexing, Git, or live diagnostic execution at startup;
- demo startup does not persist repository bindings or create snapshot lock
  files;
- analysis requests have rate, concurrency, and timeout limits;
- WebMCP tools expose read-only analysis operations only.

The web gateway does not provide user authentication, authorization, TLS
termination, or multi-tenant isolation. Do not expose local mode directly to
an untrusted network. A public deployment must add an appropriate reverse
proxy or platform access control, TLS, resource limits, and operational
monitoring.

The generated Code City page currently loads its visualization dependencies
from a third-party CDN. Deployments with strict supply-chain or offline
requirements should provide an independently reviewed local asset policy.

## Secret Handling

- Never commit API keys, passwords, tokens, private repository URLs, or model
  credentials.
- Keep local registries, runtime state, caches, logs, checkpoints, and generated
  repository artifacts out of commits and release archives.
- Review generated maps, diagnostics, snapshots, screenshots, and release
  assets for absolute paths or sensitive metadata before publishing them.
- Use the repository's locked dependency files and review dependency changes
  before release.

## Security Review Expectations

Changes that affect repository paths, subprocess execution, WebMCP exposure,
demo artifacts, persistence, dependencies, or HTTP behavior should include:

- input validation and allowlist tests;
- regression coverage for path traversal and cross-repository isolation;
- checks that read-only demo mode performs no unintended writes;
- sanitized error and activity logging;
- lint, tests, package inspection, and dependency/security scanning.
