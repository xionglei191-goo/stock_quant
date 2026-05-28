# PR And Merge Checklist

## Required
- [ ] Scope matches one task ID from `tasks/todo.md`
- [ ] Owner group is clearly defined and single-threaded for the touched area
- [ ] Tests relevant to the change were run and results recorded
- [ ] No secrets, tokens, or local credential material were introduced
- [ ] Documentation impacted by the change was updated

## Multi-Agent Handoff Requirement
- [ ] If this PR continues, modifies, or closes work that changed hands across agents or groups, the corresponding file in `docs/agent-handoffs/` was created or updated
- [ ] The handoff document includes current status, exact touched files, validation commands, known risks, and next action
- [ ] If no handoff update was needed, the PR description states why

## Merge Gate
- [ ] Reviewer confirmed the handoff record is consistent with the code change
- [ ] Reviewer confirmed `tasks/todo.md` status is still accurate
- [ ] Reviewer confirmed validation evidence is reproducible
