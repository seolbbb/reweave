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

## CRITICAL: PRODUCT STRATEGY AND PROGRESS TRACKING

`docs/PRODUCT_STRATEGY_AND_ROADMAP.md` is the canonical product strategy,
competitive rationale, roadmap, decision log, and delivery tracker for Reweave.

For every task in this repository, agents and contributors MUST:

1. Read `docs/PRODUCT_STRATEGY_AND_ROADMAP.md` before planning or changing work.
2. Add or update an entry in its **Current Delivery Tracker** or **Task Work Log**
   before implementation begins. Use `Maintenance / Other` when the task does
   not map directly to a roadmap phase.
3. Keep the entry current when scope, status, assumptions, or blockers change.
4. Before declaring completion, record the outcome, validation evidence, tests,
   and executable build result when the build requirement applies.
5. Record product or architecture choices in the **Decision Log**, including the
   reason and any superseded decision.

Allowed task statuses are `Not started`, `In progress`, `Blocked`, `Deferred`,
and `Complete`. Never mark an item `Complete` without evidence. Do not erase
historical work-log or decision-log entries; supersede them with a new dated
entry when direction changes.

Updating the strategy document is part of the definition of done for every
task, including bug fixes, documentation, refactors, research, and maintenance.
An explicit user instruction can override the current strategy, but the
override and its rationale MUST be recorded in the document.

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
