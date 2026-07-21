# AGENTS.md

## CRITICAL: PULL REQUEST TARGET BRANCH (NEVER DELETE THIS SECTION)

> **THIS SECTION MUST NEVER BE REMOVED OR MODIFIED**

### Git Workflow

```
main (deployed/published)
   ↑
  dev (integration branch)
   ↑
feature branches (your work)
```

### Rules (MANDATORY)

| Rule | Description |
|------|-------------|
| **ALL PRs → `dev`** | Every pull request MUST target the `dev` branch |
| **NEVER PR → `main`** | PRs to `main` are **automatically rejected** by CI |
| **"Create a PR" = target `dev`** | When asked to create a new PR, it ALWAYS means targeting `dev` |
| **Merge commit ONLY** | Squash merge is **disabled** in this repo. Always use merge commit when merging PRs. |

### Why This Matters

- `main` = production/published npm package
- `dev` = integration branch where features are merged and tested
- Feature branches → `dev` → (after testing) → `main`
- Squash merge is disabled at the repository level — attempting it will fail

**If you create a PR targeting `main`, it WILL be rejected. No exceptions.**

---

## DEFAULT: COMPLETE THE DELIVERY LOOP

Unless the user explicitly limits a task to planning, audit, local-only work, or another
pre-integration boundary, every requested implementation task MUST continue through the full
repository delivery loop without asking for routine confirmation:

1. Verify the completed implementation and required Windows executable build.
2. Create intentional English commits split by functional unit.
3. Push the feature branch and open a pull request targeting `dev`.
4. Merge the pull request into `dev` with a merge commit after required checks pass.
5. Merge the verified `dev` branch into `main` with a merge commit and push `main`.
6. Re-observe local and remote branch tips and report the final integration evidence.

Do not stage unrelated user changes, bypass required checks, squash commits, target a pull
request at `main`, or deploy/publish outside the repository unless the user separately
authorizes that external action.

---

## CRITICAL: ENGLISH-ONLY POLICY (NEVER DELETE THIS SECTION)

> **THIS SECTION MUST NEVER BE REMOVED OR MODIFIED**

### All Project Communications MUST Be in English

| Context | Language Requirement |
|---------|---------------------|
| **GitHub Issues** | English ONLY |
| **Pull Requests** | English ONLY (title, description, comments) |
| **Commit Messages** | English ONLY |
| **Code Comments** | English ONLY |
| **Documentation** | English ONLY |
| **AGENTS.md files** | English ONLY |

**If you're not comfortable writing in English, use translation tools. Broken English is fine. Non-English is not acceptable.**

---

## Project Overview

- **Repository:** `seolbbb/reweave`
- **Language:** Python
- **License:** MIT

---

## Structure

Reweave is a local archive/search app for AI conversation exports.

```
reweave/
├── frontend/           # React/Vite local web app
├── src/reweave/        # Python CLI, archive, API, and insight code
├── tests/              # Python tests
├── .gitignore          # Python-specific gitignore
├── LICENSE             # MIT License
├── README.md           # Project readme
└── AGENTS.md           # This file
```

---

## CRITICAL: CANONICAL PRODUCT RECORD AND PROGRESS TRACKING

Reweave uses four canonical documents with non-overlapping responsibilities:

| Document | Source of truth |
|---|---|
| `docs/PRODUCT_SPEC.md` | Intended product behavior, users, values, scope, safety, privacy, and acceptance |
| `docs/ROADMAP.md` | Delivery order, phase dependencies, tasks, and exit evidence |
| `docs/PROJECT_STATUS.md` | Current observed implementation, drift, blockers, verification, and exactly one Next task |
| `docs/DECISION_LOG.md` | Consequential user interventions, protected values, rationale, rejected alternatives, and supersession history |

`docs/PRODUCT_STRATEGY_AND_ROADMAP.md` is a preserved historical strategy,
competitive-research, and delivery record. It is not the active product contract.

For every task in this repository, agents and contributors MUST:

1. Read `docs/PRODUCT_SPEC.md`, `docs/PROJECT_STATUS.md`, `docs/ROADMAP.md`, then
   the relevant entries in `docs/DECISION_LOG.md` before planning or changing work.
2. Re-observe Git, code, tests, and runtime behavior. Treat those observations as
   truth for what exists now and record conflicts with the intended Product Spec
   as drift in `PROJECT_STATUS.md`.
3. Before implementation begins, confirm that `PROJECT_STATUS.md` contains exactly
   one concrete Next task represented in `ROADMAP.md` with acceptance and
   verification details.
4. Keep phase and task state current from evidence. Never infer completion from
   prose, a checkbox, or a historical commit hash.
5. Record consequential product or architecture changes in `DECISION_LOG.md`.
   Preserve and link superseded decisions in both directions instead of
   rewriting history.
6. Update every affected canonical document in the same task as implementation.
7. Before completion, record exact validation evidence, tests, executable build
   result when applicable, remaining drift, and the one new Next task.
8. Run the installed `manage-project-intent` validator:

    & ".venv\Scripts\python.exe" "$env:USERPROFILE\.codex\skills\manage-project-intent\scripts\validate_project_docs.py" --root "." --strict full

An explicit user instruction can override the current Product Spec, but the
override, protected value, affected roadmap work, and superseded decisions MUST
be recorded before implementation.

---

## CRITICAL: COMPLETION REQUIRES A WINDOWS EXECUTABLE BUILD

Every implementation task MUST include a fresh PyInstaller build before the work is considered complete.

1. If frontend files changed, run `npm run build` from `frontend/` first so the packaged web assets are current.
2. From the repository root, run:

   ```powershell
   .venv\Scripts\pyinstaller.exe --noconfirm --clean packaging\Reweave.spec
   ```

3. Confirm that `dist\Reweave\Reweave.exe` was created successfully.
4. Report the PyInstaller build result in the final response.

Do not mark any task complete or create its final commit until this executable build succeeds.

<!-- manage-project-intent:start -->
## Project record and continuity

- Read `docs/PRODUCT_SPEC.md`, `docs/PROJECT_STATUS.md`, `docs/ROADMAP.md`, then relevant entries in `docs/DECISION_LOG.md` before product-behavior work.
- Treat code, tests, and observed runtime behavior as truth for current implementation; treat `PRODUCT_SPEC.md` as truth for intended behavior.
- Record conflicts as drift in `PROJECT_STATUS.md` instead of silently choosing one source.
- Keep exactly one concrete Next task with acceptance and verification details in `PROJECT_STATUS.md`.
- Preserve user interventions, protected values, rejected alternatives, and superseded decisions in `DECISION_LOG.md`.
- Update affected project documents in the same task as implementation and run the `$manage-project-intent` document validator before completion.
<!-- manage-project-intent:end -->
