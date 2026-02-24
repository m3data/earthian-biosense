# Spawn Guide — RAA-EBS-001

## Prerequisites

- Hence v0.6.x installed (`hence --version`)
- This directory is a git repo (already initialised)
- Initial commit includes plan.spl + CLAUDE.md + empty findings dirs

## Known Issues

- `hence watch --spawn` does NOT work — use manual spawns below
- Parallel spawns cause plan.spl merge conflicts — copy findings from worktrees manually
- Agent scope can drift — check output files match expected task scope

## Phase A — Independent Audit (parallel)

Run all at once. Each spawns in its own worktree:

```bash
hence spawn plan.spl --agent claude --task a1-hrv-metrics-clinical-accuracy
hence spawn plan.spl --agent claude --task a2-entrainment-breath-heart-coupling
hence spawn plan.spl --agent claude --task a3-phase-space-dynamics-validity
hence spawn plan.spl --agent claude --task a4-mode-classification-soft-membership
hence spawn plan.spl --agent claude --task a5-architecture-separation-of-concerns
```

**After all complete:** Copy findings from worktrees to main repo:

```bash
cp .claude/worktrees/*/findings-a/01-hrv-metrics-clinical-accuracy.md findings-a/
cp .claude/worktrees/*/findings-a/02-entrainment-breath-heart-coupling.md findings-a/
cp .claude/worktrees/*/findings-a/03-phase-space-dynamics-validity.md findings-a/
cp .claude/worktrees/*/findings-a/04-mode-classification-soft-membership.md findings-a/
cp .claude/worktrees/*/findings-a/05-architecture-separation-of-concerns.md findings-a/
```

Then mark completions:

```bash
hence complete plan.spl a1-hrv-metrics-clinical-accuracy --agent claude
hence complete plan.spl a2-entrainment-breath-heart-coupling --agent claude
hence complete plan.spl a3-phase-space-dynamics-validity --agent claude
hence complete plan.spl a4-mode-classification-soft-membership --agent claude
hence complete plan.spl a5-architecture-separation-of-concerns --agent claude
```

## Phase A Synthesis

```bash
hence spawn plan.spl --agent claude --task a-synthesis
```

Copy output:

```bash
cp .claude/worktrees/*/findings-a/SYNTHESIS-A.md findings-a/
```

```bash
hence complete plan.spl a-synthesis --agent claude
```

## Phase B — Adversarial Counter-Audit (parallel)

```bash
hence spawn plan.spl --agent claude --task b1-counter-hrv-metrics-clinical-accuracy
hence spawn plan.spl --agent claude --task b2-counter-entrainment-breath-heart-coupling
hence spawn plan.spl --agent claude --task b3-counter-phase-space-dynamics-validity
hence spawn plan.spl --agent claude --task b4-counter-mode-classification-soft-membership
hence spawn plan.spl --agent claude --task b5-counter-architecture-separation-of-concerns
```

**After all complete:** Copy findings from worktrees:

```bash
cp .claude/worktrees/*/findings-b/01-counter-hrv-metrics-clinical-accuracy.md findings-b/
cp .claude/worktrees/*/findings-b/02-counter-entrainment-breath-heart-coupling.md findings-b/
cp .claude/worktrees/*/findings-b/03-counter-phase-space-dynamics-validity.md findings-b/
cp .claude/worktrees/*/findings-b/04-counter-mode-classification-soft-membership.md findings-b/
cp .claude/worktrees/*/findings-b/05-counter-architecture-separation-of-concerns.md findings-b/
```

Then mark completions:

```bash
hence complete plan.spl b1-counter-hrv-metrics-clinical-accuracy --agent claude
hence complete plan.spl b2-counter-entrainment-breath-heart-coupling --agent claude
hence complete plan.spl b3-counter-phase-space-dynamics-validity --agent claude
hence complete plan.spl b4-counter-mode-classification-soft-membership --agent claude
hence complete plan.spl b5-counter-architecture-separation-of-concerns --agent claude
```

## Evaluator — Convergence Assessment

```bash
hence spawn plan.spl --agent claude --task convergence-eval
```

Copy output:

```bash
cp .claude/worktrees/*/CONVERGENCE-REPORT.md .
```

```bash
hence complete plan.spl convergence-eval --agent claude
```

## Cleanup

List worktrees: `git worktree list`
Remove all: `git worktree list --porcelain | grep "^worktree " | cut -d' ' -f2 | xargs -I{} git worktree remove {}`
