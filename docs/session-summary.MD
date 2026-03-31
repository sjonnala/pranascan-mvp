# OpenClaw AI OS — Complete Setup Summary

**Version:** 1.0  
**Built:** March 2026  
**Platform:** Ubuntu VM + Claude Code CLI  
**Purpose:** Modular, project-aware, agent orchestration OS with controlled context, runtime isolation, and extensible workflows

---

## What Is OpenClaw AI OS?

OpenClaw is a **shell-based AI operating system** that runs on your Ubuntu VM. It transforms Claude from a chat assistant into a structured, multi-agent development team — with persistent memory, task state tracking, quality gates, and error recovery.

**The mental model:**
```
You          = CEO
OpenClaw     = Project Management System (the OS)
Claude CLI   = The talent pool (called as different specialists)
CLAUDE.md    = Job description for each specialist
$CLAW_MEMORY = Shared team memory that persists between sessions
```

Every time you run `claw-dispatch`, OpenClaw assembles a complete context packet — identity, project decisions, task state, prior work — and calls `claude --print` with it. Claude responds as the assigned specialist. The response is saved to disk and the task state machine advances automatically.

---

## System Architecture — Big Picture

```
┌─────────────────────────────────────────────────────────────────┐
│  YOU                                                            │
│  Browser chat (thinking/planning) + CLI (execution)            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    claw-dispatch
                           │
         ┌─────────────────▼──────────────────┐
         │         CONTEXT ASSEMBLY           │
         │  1. SOUL.md (personality)          │
         │  2. Agent CLAUDE.md (role)         │
         │  3. director/decisions.md          │
         │  4. handoffs/<TASK_ID>.yaml        │
         │  5. Prior artifacts from memory    │
         │  6. Task instruction               │
         └─────────────────┬──────────────────┘
                           │
                    claude --print
                           │
         ┌─────────────────▼──────────────────┐
         │         AGENT RESPONSE             │
         │  Saved to $CLAW_MEMORY/<agent>/    │
         │  Handoff YAML updated              │
         │  Next agent determined             │
         └────────────────────────────────────┘
```

---

## Directory Structure — Complete

```
~/.openclaw/
│
├── SOUL.md                          ← Global personality injected into every agent
│
├── agents/
│   └── registry/                   ← One folder per agent
│       ├── director/CLAUDE.md
│       ├── pm/CLAUDE.md
│       ├── eng/CLAUDE.md
│       ├── code_reviewer/CLAUDE.md
│       ├── security/CLAUDE.md
│       ├── ops/CLAUDE.md
│       └── research/CLAUDE.md
│
├── config/
│   ├── agents_registry.yaml        ← Master list of all agents and their roles
│   └── defaults.yaml               ← Default agents loaded for any project
│
├── projects/
│   └── <project_name>.yaml         ← One file per project (e.g. pranascan.yaml)
│
├── runtime/
│   └── active_agents.yaml          ← Which agents are active right now
│
├── lib/
│   └── claw-guards.sh              ← Shared validation library sourced by all scripts
│
├── scripts/                        ← All CLI commands (on your PATH)
│   ├── claw-project                ← Entry point: activate a project
│   ├── claw-task                   ← Create a new task
│   ├── claw-dispatch               ← Invoke an agent with assembled context
│   ├── claw-handoff-update         ← Advance task state in handoff YAML
│   ├── claw-status                 ← View task board
│   ├── claw-context                ← Debug: print context without invoking claude
│   ├── claw-memory-init            ← Scaffold memory namespace for a new project
│   ├── claw-rollback               ← Execute image rollback after failed deploy
│   ├── claw-escalate               ← Block/override/reset/split tasks
│   ├── claw-unblock                ← Human provides resolution to unblock a task
│   ├── claw-retry                  ← Re-enter pipeline after a fix
│   └── claw-doctor                 ← Full system diagnostic
│
├── memory/
│   └── <project_name>/             ← Isolated namespace per project
│       ├── handoffs/               ← Task state files (one YAML per task)
│       ├── director/
│       │   ├── task_log.md         ← Append-only log of all tasks
│       │   └── decisions.md        ← Key decisions injected into every agent
│       ├── pm/
│       │   ├── specs/              ← One spec per task
│       │   └── backlog.md          ← Queued tasks not yet specced
│       ├── eng/
│       │   ├── implementations/    ← One implementation summary per task
│       │   ├── decisions.md        ← ADR-style engineering decisions
│       │   └── FUTURE.md           ← Out-of-scope ideas captured during build
│       ├── code_reviewer/
│       │   ├── reviews/            ← Approved/rejected review files
│       │   └── patterns.md         ← Recurring issues observed over time
│       ├── security/
│       │   ├── reviews/            ← Cleared/blocked security review files
│       │   ├── advisories.md       ← Non-blocking security observations
│       │   └── threat_model.md     ← Living threat model for the project
│       ├── ops/
│       │   ├── deployments/        ← Deployment success/failure records
│       │   ├── runbooks/           ← Operational procedures (rollback, migration)
│       │   └── infra_changes.md    ← Append-only infrastructure change log
│       └── research/
│           ├── findings/           ← One findings doc per investigation
│           └── library.md          ← Reusable reference index (check before re-researching)
│
├── memory-spec/
│   ├── MEMORY_SPEC.md              ← Authoritative memory format specification
│   └── templates/                  ← Output templates for each agent artifact
│       ├── pm/spec.md
│       ├── eng/implementation.md
│       ├── code_reviewer/review-approved.md
│       ├── code_reviewer/review-rejected.md
│       ├── security/review-cleared.md
│       ├── security/review-blocked.md
│       ├── ops/deployment-success.md
│       ├── ops/deployment-failed.md
│       ├── ops/runbooks/migration-recovery.md
│       ├── research/findings.md
│       └── director/task_log_entry.md
│
├── handoffs/
│   ├── schema.yaml                 ← Handoff file schema reference
│   └── example_feat-001.yaml       ← Worked example of a full task lifecycle
│
├── error-spec/
│   └── ERROR_ROLLBACK_SPEC.md      ← All failure modes and recovery procedures
│
├── HANDOFF_PROTOCOL.md             ← How agents communicate and pass context
└── install.sh                      ← Full system installer
```

---

## The 7 Agents — What Each One Does

### Director
**Role:** Orchestrator — the only agent that talks to you  
**What it does:** Receives raw requests, clarifies intent, decomposes into tasks, routes to the right agent, synthesises final responses  
**Key constraint:** Never writes code, specs, or deploys. Always delegates.  
**Memory:** `director/task_log.md`, `director/decisions.md`

### PM (Product Manager)
**Role:** Planner — turns intent into executable specifications  
**What it does:** Writes user stories, acceptance criteria, API contracts, edge cases, explicit out-of-scope sections  
**Key constraint:** Never writes code. One spec per deployable unit of behaviour.  
**Memory:** `pm/specs/<TASK_ID>.md`, `pm/backlog.md`

### ENG (Engineer)
**Role:** Builder — produces all code, tests, and API contracts  
**What it does:** Implements features exactly as specced, applies domain-driven design, writes unit + integration tests, documents decisions  
**Stack awareness:** Java 21 Spring Boot modular monolith / React Native Expo / Next.js 14  
**Key constraint:** Never builds outside the spec. Never merges own code.  
**Memory:** `eng/implementations/`, `eng/decisions.md`, `eng/FUTURE.md`

### Code Reviewer
**Role:** Quality gate between eng and deployment  
**What it does:** Verifies correctness against pm spec, checks security surface, code quality, test coverage, stack compliance  
**Key behaviour:** Pulls the original pm spec to verify completeness — not just "does the code look right"  
**Memory:** `code_reviewer/reviews/`, `code_reviewer/patterns.md`

### Security
**Role:** Compliance and security gate before production  
**What it does:** HIPAA-aligned PHI checks, auth/authz verification, injection surface review, secrets management, infrastructure posture  
**Severity levels:** critical → stop everything | high → block | medium → block | advisory → approve with note  
**Memory:** `security/reviews/`, `security/advisories.md`, `security/threat_model.md`

### OPS
**Role:** Executor — deploys and operates the runtime  
**What it does:** Executes deployments, runs Flyway migrations, health checks, rollbacks, logs all infrastructure changes  
**Key constraint:** Never deploys without code_reviewer approval. Never deploys to production without security clearance.  
**Memory:** `ops/deployments/`, `ops/runbooks/`, `ops/infra_changes.md`

### Research
**Role:** Investigator — resolves unknowns before planning begins  
**What it does:** Investigates options, evaluates tradeoffs, runs spikes, always returns a recommendation (never open-ended)  
**Key constraint:** Time-boxed. Every output ends with a clear recommendation.  
**Memory:** `research/findings/`, `research/library.md`

---

## The 5 Gaps — What Was Built and Why

### Gap 1: Agent CLAUDE.md Files
**Problem:** Without identity files, Claude has no persistent persona — every invocation starts from scratch with no role, constraints, or output contract.  
**Solution:** One `CLAUDE.md` per agent with a consistent schema: Identity → Scope → Constraints → Input Contract → Output Contract → Handoff Protocol → Memory.  
**Result:** 7 agents with well-defined, composable identities.

### Gap 2: Agent Handoff Protocol
**Problem:** Agents were isolated silos — no mechanism to pass work, context, or state between them.  
**Solution:** File-based handoff YAML (`$CLAW_MEMORY/handoffs/<TASK_ID>.yaml`) as the shared source of truth. A 10-state task machine governs all transitions. `claw-dispatch` assembles context and drives the chain automatically.  
**Result:** Full pipeline from `director → pm → eng → code_reviewer → security → ops` with automatic routing.

### Gap 3: Memory Format Specification
**Problem:** Handoff files referenced artifact paths but nothing defined what was inside them — every agent would invent its own format.  
**Solution:** Master `MEMORY_SPEC.md` with 5 principles, complete directory layout, naming conventions, and 10 artifact templates (one per agent output type).  
**Result:** Every artifact is structured, self-contained, and predictably addressable by `claw-dispatch`.

### Gap 4: Error/Rollback Paths
**Problem:** Any failure became a manual fire drill — no defined response for deployment failures, migration issues, infinite review loops, or blocked tasks.  
**Solution:** 4-class failure taxonomy (Deployment / Migration / Revision Limit / Hard Block) with dedicated scripts for each recovery path. Flyway migration recovery runbook covers all sub-cases including the dangerous forward-fix path.  
**Result:** Every failure mode has a defined owner, response, and recovery procedure.

### Gap 5: Dependency Guards + Hardening
**Problem:** Scripts had ad-hoc guards, no shared validation, no diagnostic tool, and the entry point was fragile.  
**Solution:** `claw-guards.sh` shared library (20+ guard functions), hardened 7-phase `claw-project` entry point, `claw-doctor` diagnostic runner, unified installer.  
**Result:** System fails fast and clearly. `claw-doctor` gives a full health view in one command.

---

## The Task State Machine — 10 States

```
CREATED → RESEARCHING → PLANNING → BUILDING → REVIEWING
                                       ↑            │
                                       └────────────┘ (on rejection)
                                                    │
                                          ┌─────────┴─────────┐
                                    [non-prod]           [production]
                                          │                    │
                                      DEPLOYING           SECURITY
                                          │                    │
                                       DONE              DEPLOYING
                                                              │
                                                           DONE
Special states: BLOCKED, CANCELLED
```

**Valid transitions are strict** — no agent can skip a gate. The revision limit (3 rejections) forces director intervention before eng can be invoked again.

---

## The Handoff File — The System's Single Source of Truth

Every task is a YAML file at `$CLAW_MEMORY/handoffs/<TASK_ID>.yaml`:

```yaml
task_id: feat-001
project: pranascan
status: REVIEWING              ← current state
current_agent: code_reviewer   ← who acts next
deploy_target: production
priority: high
revision_count: 1              ← rejections so far
created_at: 2026-03-31T...
updated_at: 2026-03-31T...

request:
  summary: "Patient can book a video consultation"
  requested_by: user

chain:                         ← append-only audit trail
  - agent: director
    action: created
    timestamp: ...
    output_ref: null
  - agent: pm
    action: planned
    output_ref: pm/specs/feat-001.md
  - agent: eng
    action: implemented
    output_ref: eng/implementations/feat-001.md
  - agent: code_reviewer
    action: rejected
    rejection_ref: code_reviewer/reviews/feat-001-rejected.md
  - agent: eng
    action: revised
    output_ref: eng/implementations/feat-001-r1.md
```

The `chain` array is **append-only** — history is never deleted. This gives a complete audit trail of every action taken on every task.

---

## Context Assembly — What Claude Sees on Every Dispatch

When `claw-dispatch task-001 pm` runs, it assembles this context in order:

```
1. ~/.openclaw/SOUL.md
   → Your core personality and principles

2. ~/.openclaw/agents/registry/pm/CLAUDE.md
   → PM identity, scope, constraints, input/output contracts

3. $CLAW_MEMORY/director/decisions.md
   → Key project decisions + your USER.md preferences

4. $CLAW_MEMORY/handoffs/task-001.yaml
   → Current task state, priority, deploy target, full chain

5. Referenced artifacts (last 3, most recent first)
   → What prior agents produced on this task

6. Task instruction
   → "Your task: write a spec for task-001"
```

This is why the system works without a persistent conversation — every dispatch is self-contained but fully informed.

---

## Error Recovery — 4 Failure Classes

| Class | Trigger | Owner | Response |
|-------|---------|-------|----------|
| A — Deployment failure | Health check fails, build fails | ops | `claw-rollback` → routes back to eng |
| B — Migration failure | Flyway mid-apply, schema incompatible | ops → director | Freeze → assess → repair or forward-fix |
| C — Revision limit | eng rejected 3+ times | director | `claw-escalate` → clarify/split/override |
| D — Hard block | Security critical, human decision needed | director | `claw-escalate block` → `claw-unblock` |

**The invariants that are never violated:**
- A BLOCKED task is never auto-resumed — only `claw-unblock` can resume it
- A failed migration is never re-run without `flyway repair` first
- Production never deploys without both code_reviewer approval and security clearance

---

## CLI Command Reference

| Command | What it does |
|---------|-------------|
| `claw <project>` | Activate a project — runs 7 validation phases |
| `claw-task "summary" --priority high --target production` | Create a new task |
| `claw-dispatch <id> <agent>` | Invoke an agent — assembles context, calls claude, advances state |
| `claw-status` | View full task board |
| `claw-status <id>` | View single task detail + chain history |
| `claw-context <id> <agent>` | Debug: print assembled context without invoking claude |
| `claw-handoff-update <id> <agent> <status>` | Manually force a state transition |
| `claw-memory-init <project>` | Scaffold memory namespace for a new project |
| `claw-rollback <id> <service> <image>` | Execute deployment rollback with safety checks |
| `claw-escalate <id> block --reason "..."` | Block a task, freeze it |
| `claw-escalate <id> override --reason "..." --approved-by director` | Director bypasses code_reviewer |
| `claw-escalate <id> reset-revisions --reason "..."` | Reset eng revision count |
| `claw-escalate <id> split --into "task 1" "task 2"` | Cancel and split into simpler tasks |
| `claw-unblock <id> --resolution "..."` | Human provides input, task resumes |
| `claw-retry <id>` | Re-enter review pipeline after a fix |
| `claw-doctor` | Full system health diagnostic |
| `claw-doctor --quick` | Deps + env only (no project checks) |
| `claw-doctor --fix` | Attempt auto-repair of common issues |

---

## Typical First Run — End to End

```bash
# 1. Activate project
claw pranascan

# 2. Create a task
claw-task "Analyse PPG signal quality from camera input" \
  --priority high --target dev

# 3. Walk the chain
claw-dispatch task-001 director       # routes → research (unknown) or pm (clear)
claw-dispatch task-001 research       # if unknown — returns recommendation
claw-dispatch task-001 pm             # writes spec
claw-dispatch task-001 eng            # implements
claw-dispatch task-001 code_reviewer  # reviews
claw-dispatch task-001 ops            # deploys to dev

# 4. Check the board at any point
claw-status
claw-status task-001
```

---

## Stitching Your Existing Files Into OpenClaw

If you have existing project files (`SOUL.md`, `USER.md`, `MEMORY.md`, `AGENTS.md`), they map directly into OpenClaw:

| Your file | Where it goes in OpenClaw | Effect |
|-----------|--------------------------|--------|
| `SOUL.md` | `~/.openclaw/SOUL.md` | Injected as first context block into every agent dispatch |
| `USER.md` | Appended to `$CLAW_MEMORY/director/decisions.md` | Every agent knows your preferences |
| `MEMORY.md` | Appended to `$CLAW_MEMORY/research/library.md` | Research agent checks this before re-investigating |
| `AGENTS.md` | Merge unique behaviours into relevant `CLAUDE.md` files | Preserves your custom agent definitions |

```bash
# One-time migration
cp ~/pranascan-mvp/SOUL.md ~/.openclaw/SOUL.md
cat ~/pranascan-mvp/USER.md >> ~/.openclaw/memory/pranascan/director/decisions.md
cat ~/pranascan-mvp/MEMORY.md >> ~/.openclaw/memory/pranascan/research/library.md
```

---

## Browser Chat vs CLI — How to Use Both

| Browser Chat (this session) | CLI on Ubuntu VM |
|----------------------------|-----------------|
| Thinking, planning, brainstorming | Executing the workflow |
| Reviewing outputs, giving feedback | Creating and tracking tasks |
| Making architectural decisions | Dispatching agents |
| Drafting specs before running pm | Persisting state to memory |
| No persistent state | Full persistent state in `$CLAW_MEMORY` |

**The flow:** Think in chat → decide → `claw-task` → `claw-dispatch` → results in memory → review in chat → next task.

When you make a key decision in browser chat, log it so agents see it:
```bash
cat >> ~/.openclaw/memory/pranascan/director/decisions.md << 'EOF'

---
**[DECISION]** 2026-03-31
**Topic:** PPG signal library choice
**Decision:** Using MediaPipe — better mobile performance, no native deps
EOF
```

---

## Current System Status

```
claw-doctor results:
  ✅ yq 4.44 installed
  ✅ claude CLI installed (Claude Code 2.1.88)
  ✅ docker installed and running
  ✅ curl available
  ✅ jq available
  ✅ flyway installed
  ✅ OPENCLAW_DIR set
  ✅ Scripts on PATH
  ✅ All 12 scripts present and executable
  ✅ Guard library present
  ✅ agents_registry.yaml valid (7 agents)
  ✅ All 7 agent CLAUDE.md files present
  ✅ defaults.yaml valid
  ✅ All systems operational
```

**Active projects:** `pranascan` (PPG signal processing), `healthplatform` (three-sided healthcare MVP)

---

## What's Next

1. **First real task on pranascan** — run a codebase audit task through the full chain to validate the workflow end to end
2. **Patch `claw-dispatch` to inject `SOUL.md`** — makes every agent call personality-aware
3. **Build project config for healthplatform** — separate memory namespace for the three-sided MVP
4. **Install Claude Code on PATH globally** — ensure `claude` is available from any directory
5. **Review `pranascan-mvp` codebase through OpenClaw** — let research + pm build a prioritised gap list before eng writes anything new