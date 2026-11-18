# Security Policy

## Reporting a vulnerability
Please do not open a public issue. Use GitHub's "Report a vulnerability" (private advisory) on this repository.
Expect an acknowledgement within 7 days.

## Scope and data handling
- Uploaded documents and queries are sent to the configured LLM provider. Use a local provider (Ollama) or enable PII redaction
  when handling sensitive material. See docs/TARGET_ARCHITECTURE.md section 12 and the threat model (docs/THREAT_MODEL.md, Phase 8).
- Documents are treated as untrusted input (prompt-injection defences are part of the design).

## Known issues in the legacy prototype
Tracked in docs/AUDIT.md. The legacy upload path-traversal bug is fixed in this branch; the legacy code still has no authentication
and must not be exposed to untrusted networks.
