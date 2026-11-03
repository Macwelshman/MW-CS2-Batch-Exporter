# AI Workflow Modes

If no mode is given, use the most conservative appropriate mode (default:
INSPECT).

## INSPECT

Read/investigate only. No changes.

## DEBUG

Read AGENTS.md and PROJECT_STATUS.md. Investigate the reported problem and
establish evidence/root cause. Do not modify files until authorised.

## IMPLEMENT

Read project instructions/status. Make the smallest authorised change. Perform
appropriate focused validation. Report changes and tests actually run.

## REVIEW

Review existing changes without modifying them. Check for regressions,
relevant Blender compatibility issues and violations of AGENTS.md.

## RELEASE

Check implementation, tests, documentation, metadata and packaging. Do not
version, package, commit, tag or publish unless explicitly requested.
