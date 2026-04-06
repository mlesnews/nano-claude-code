# Sovereign Harness — Implementation Roadmap

**Ticket:** C-000003916
**Owner:** Cedarbrook Financial Services LLC
**Decision gate:** April 30, 2026

---

## Phase 1 — Foundation (DONE)

**Dates:** March 28 – April 4, 2026
**Estimated hours:** 16h (actual: ~18h)

### Deliverables
- [x] Fork nano-claude-code from SafeRL-Lab/nano-claude-code
- [x] Build lumina-hook-engine as standalone pip-installable library
- [x] HookDef / HookGroup / HookResult dataclasses
- [x] Engine runner with timeout, async, and result merging
- [x] Test suite passing for hook engine
- [x] Upstream tracking configured (rebase-friendly)

### Dependencies
- None (greenfield)

### Success Criteria
- `pytest tests/` passes in lumina-hook-engine repo
- nano-claude-code fork builds and runs unmodified
- Both repos pushed to mlesnews GitHub org

---

## Phase 2 — Hook Integration (THIS WEEK: Apr 4–11)

**Estimated hours:** 20h

### Deliverables
- [ ] Add `lumina-hook-engine` as dependency in nano-claude-code
- [ ] Wire `HookEngine.run()` into `agent.py` at PreToolUse / PostToolUse points
- [ ] Port existing Claude Code hooks (settings.json format) to Python hook commands
- [ ] Implement hook categories:
  - Security: compusec_guard, vault enforcement, secret scan
  - Governance: ticket-gate (require ticket ID), ITIL change approval
  - Context: memory injection, context budget check
  - Coding: pre-commit lint, test runner, format check
  - Safety: destructive-op blocker (rm -rf, git push --force)
  - Telemetry: cost tracker, latency logger
  - Routing: model-selection hints based on task type
- [ ] Validate all 49 hooks fire correctly in integration tests
- [ ] Config loader: read hooks from `settings.json` or `hooks.yaml`

### Dependencies
- Phase 1 complete
- nano-claude-code agent.py tool execution loop understood

### Success Criteria
- `compusec_guard` blocks secret exposure in tool output
- Destructive-op hook blocks `rm -rf /` before execution
- All 49 hooks have at least one integration test
- No regression in existing nano-claude-code test suite

---

## Phase 3 — Provider Router + Context Governor (Post Apr 30)

**Estimated hours:** 30h

### Deliverables
- [ ] Provider router: route requests by task type / cost / latency
  - Cheap tasks (grep, ls) → local model or GPT-4o-mini
  - Complex reasoning → Claude Opus / Sonnet
  - Code generation → configurable default
  - Fallback chain: primary → secondary → tertiary
- [ ] EMM386 v2 context governor port from current Claude Code hooks
  - Token budget tracking per conversation
  - Transparent compression with configurable strategy
  - Memory tier integration (hot/warm/cold)
- [ ] Status line driver: live token count, model name, cost, hook status
- [ ] Provider health check and automatic failover

### Dependencies
- Phase 2 complete (hooks wired in)
- API keys for Claude, GPT, Gemini configured

### Success Criteria
- Router correctly selects model based on task classification
- Context governor keeps conversations under token budget
- Status line updates in real-time during agent loop
- Failover triggers within 5s of provider timeout

---

## Phase 4 — Squad System + IPC (May 2026)

**Estimated hours:** 25h

### Deliverables
- [ ] Squad launcher: spawn N parallel agent instances
- [ ] IPC protocol between squad members (shared memory or Unix sockets)
- [ ] Task distribution: assign sub-tasks to squad members by specialty
- [ ] Result aggregation: collect and merge outputs from parallel agents
- [ ] Squad lifecycle: health monitoring, restart on failure, graceful shutdown
- [ ] Integration with existing `/squad` skill from Claude Code

### Dependencies
- Phase 3 complete (router + governor working)
- nano-claude-code subagent.py architecture understood

### Success Criteria
- 4 parallel agents run without resource conflicts
- Sub-task results merge correctly into parent context
- Squad survives one member crashing without data loss
- Measurable speedup on parallelizable tasks (file search, multi-file edit)

---

## Phase 5 — Daily Driver Switch (June 2026)

**Estimated hours:** 15h

### Deliverables
- [ ] Full feature parity audit vs Claude Code CLI
- [ ] Migration script: port existing CLAUDE.md, settings.json, memory
- [ ] Shell alias switch: `claude` → sovereign harness binary
- [ ] Performance benchmarking: latency, token usage, cost comparison
- [ ] Documentation: user guide, hook authoring guide, provider config
- [ ] Deprecation plan for Claude Code CLI dependency

### Dependencies
- Phases 1–4 complete and stable
- 2 weeks of parallel daily-driver testing

### Success Criteria
- All current workflows (commit, PR, code review, search) work in harness
- Cost per session reduced vs Claude-only baseline
- No critical bugs in 14 consecutive days of daily use
- User (Matt) confirms ready for full switch

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Upstream nano-claude-code breaks on rebase | Medium | Track upstream releases, rebase weekly, keep patches minimal |
| Provider API changes break router | Medium | Abstract provider interface, version-pin SDKs |
| Hook engine adds latency to every tool call | Low | Async hooks, timeout enforcement, bypass for read-only tools |
| Context governor too aggressive | Medium | Configurable thresholds, manual override, preserve pinned messages |
| Apr 30 decision gate: revenue still $0 | High | Sovereign Harness is a product candidate — demo-ready by Phase 3 |

---

## Hours Summary

| Phase | Hours | Cumulative |
|-------|-------|------------|
| 1 — Foundation | 18h | 18h |
| 2 — Hook Integration | 20h | 38h |
| 3 — Router + Governor | 30h | 68h |
| 4 — Squad/IPC | 25h | 93h |
| 5 — Daily Driver | 15h | 108h |
| **Total** | **108h** | |
