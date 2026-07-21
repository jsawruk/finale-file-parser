# Security & guardrails

The invariants Claude Code and human contributors must never trade away for convenience. The short
version lives in `CLAUDE.md`; this is the detail.

## Secrets

- Real secrets live only in a git-ignored `.env`. `.env.example` lists variable names with
  placeholder values. Never commit a real credential, key, or token.
- If a secret is ever committed by accident, treat it as compromised: rotate it, then remove it from
  history. Do not just delete it in a later commit.

## Dependencies

- Prefer well-maintained, widely-used libraries. `make check` (and CI) runs an advisory dependency
  audit; escalate flagged issues to the owner.

## Data & licensing

- Large binaries, datasets, and model weights stay out of git.
- Licensing / access tier is mandatory metadata, never defaulted to permissive. When in doubt, mark
  it OPEN in `docs/DECISIONS.md` and ask the owner.

## The meta-rule

Flag legally, ethically, or security-sensitive calls for the owner instead of deciding them.
