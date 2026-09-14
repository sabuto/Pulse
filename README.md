<div align="center">

# ⚡ Pulse

### Modern, standalone project management for Frappe

A Plane / Jira / Linear-style delivery tool that installs on **any** Frappe site with **zero dependency on ERPNext** — and can be driven by AI through a built-in MCP server.

`Frappe v16` · `Vue 3` · `frappe-ui` · `Python` · `MIT`

</div>

---

## Table of contents

- [What is Pulse](#what-is-pulse)
- [Why Pulse](#why-pulse)
- [Features](#features)
- [Screens](#screens)
- [Architecture](#architecture)
- [Installation](#installation)
- [First run](#first-run)
- [Roles & permissions](#roles--permissions)
- [AI control (MCP)](#ai-control-mcp)
- [Demo data](#demo-data)
- [Development](#development)
- [Data model](#data-model)
- [Roadmap](#roadmap)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)

---

## What is Pulse

**Pulse** is a self-contained, agile project-management application for the [Frappe framework](https://frappeframework.com). It gives delivery teams a fast, modern experience — projects, tasks with human-readable keys (`OPS-9`), a drag-and-drop board, sprints, backlog, per-user customizable dashboards, analytics, OKRs, risks, meetings, retrospectives, timesheets and a timestamped audit log — all delivered through a **Vue 3 single-page app** at `/pulse`, dark-themed by default.

Every piece of data Pulse touches is **owned by Pulse**. Nothing is linked to another app's doctypes, so it installs and runs the same on a bare Frappe site as it does alongside ERPNext.

## Why Pulse

Most Frappe-based PM tools are built *on top of* ERPNext Projects, which couples your delivery data to a full ERP and makes them impossible to run standalone. Pulse takes the opposite stance:

- **Plug-and-play** — `bench install-app pulse` works on a fresh Frappe site with **no ERPNext** required. (Verified end-to-end: installs cleanly on a site where ERPNext was never present.)
- **Owns 100% of its data** — no Pulse doctype links to a non-Pulse business doctype; only framework primitives (`User`, `Role`, `Workflow State`, `File`, …) are reused.
- **Modern UX** — a real SPA, not Desk forms: drag-drop board, command-style flows, restraint-first dark design.
- **AI-native** — ships an MCP server so assistants like Claude can create, edit, move and assign work in plain language.

## Features

### Projects & tasks
- Projects with a short **project key** (`OPS`, `PLM`) used to build task ids.
- **Human-readable task keys** — per-project running sequence (`OPS-9`, `PLS1-8`), auto-assigned on create and backfilled for existing tasks.
- Task types (Epic, Story, Bug, Feature, Improvement, Incident, Task, Sub-task) as first-class, standalone **Pulse Issue Type** records — never ERPNext's `Task Type`.
- Priority, story points, due dates, description, labels.

### Board & work views
- **Drag-and-drop board** across Backlog → To Do → In Progress → In Review → Done, with optimistic updates.
- **Board / List** view toggle.
- **Filter & search** by type, priority, assignee, and free text.
- **Inline quick-add** per column and a full **New task** dialog.
- Rich **task drawer**: edit fields, assign people, checklist, comments, **sub-tasks** (with progress), and **dependencies** ("blocked by").

### Sprints & backlog
- Create and run sprints (planned / active / completed) with dates and goals.
- Backlog view ordered by rank.

### Dashboards & analytics
- **Per-user customizable dashboards** — add / move / resize widgets (KPI cards, charts, lists); layouts persist per user; admins can set a default template.
- **Analytics** view (MindPro-style): status distribution, tasks per assignee, type distribution, a story-point completion gauge, and sprint-progress bars.

### Delivery & governance
- **OKRs** (objectives, key results, check-ins, goals).
- **Risks** with actions and linked tasks.
- **Portfolios** grouping projects.
- **Meetings** (attendees, decisions, action items), **Retrospectives**, **Documents**, **Timesheets**.

### Assignment & audit
- **Create-and-assign in one step** — pick assignees while creating a task.
- **Hierarchical assignment**, enforced server-side: a user can only assign work at or below their own role rank (juniors can't assign upward).
- **Audit log** — a timestamped, unified activity feed (creates, status changes, assignments, comments) available as its own menu.

### AI control
- A bundled **MCP server** exposes 16 tools (list / create / update / move / assign / comment / sub-task / dependency / sprint / project …) so Claude Desktop or Claude Code can operate Pulse conversationally. See [`mcp/README.md`](mcp/README.md).

## Screens

> Add screenshots/GIFs here (Home, Board, Task drawer, Dashboard, Analytics, Audit log).

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Vue 3 SPA  (frappe-ui)         served at  /pulse          │
│  Board · Backlog · Sprints · Dashboards · Analytics · …    │
└───────────────▲──────────────────────────────────────────┘
                │  thin whitelisted REST  (pulse.api.*)
┌───────────────┴──────────────────────────────────────────┐
│  Pulse app  (Frappe / Python)                             │
│  ~50 Pulse doctypes · doc-events · permission hooks ·     │
│  hierarchical assignment · reports · schedulers           │
└───────────────▲──────────────────────────────────────────┘
                │  reuses ONLY framework primitives
┌───────────────┴──────────────────────────────────────────┐
│  Frappe framework  (auth · permissions · workflow · REST) │
└──────────────────────────────────────────────────────────┘
        (no ERPNext — nothing here depends on it)
```

- **Backend:** all logic in the `pulse` app; the public API lives under the `pulse.api.*` namespace and writes go through the standard document API so permissions and validations always fire.
- **Frontend:** a Vue 3 + frappe-ui app in [`frontend/`](frontend), built to `pulse/public/frontend` and served by a small website route at `/pulse`.
- **Standalone guarantee:** no `required_apps`, no ERPNext references, and every doctype link targets a `Pulse *` doctype or a framework-core doctype.

## Installation

Prerequisites: a working [Frappe bench](https://frappeframework.com/docs/user/en/installation) (v15+/v16).

```bash
# from your bench directory
bench get-app https://github.com/sabuto/Pulse.git
bench --site your-site install-app pulse
```

### Build the frontend (only needed for a fresh git clone)

The repo ships pre-built assets, but if you're building from source:

```bash
cd apps/pulse/frontend
yarn install
yarn build
```

That's it — no ERPNext, no extra services.

## First run

- Open **`/pulse`** on your site (e.g. `http://your-site:8000/pulse`), or click the **Pulse** tile in the Frappe **apps launcher** — Pulse also adds a **Pulse** entry to the Desk sidebar.
- Pulse users land in the app automatically after login.
- Create a **Project** (give it a key like `OPS`), then start adding tasks — task ids like `OPS-1` are generated for you.

## Roles & permissions

Pulse ships these roles, ranked for the assignment hierarchy (higher = more senior):

| Role | Rank |
|---|---|
| Pulse Admin | 100 |
| Pulse Manager | 80 |
| Pulse Team Lead | 60 |
| Pulse Senior Developer | 40 |
| Pulse Junior Developer | 20 |
| Pulse Intern | 10 |
| Pulse Viewer | 0 |

A user may assign work only to people **at or below** their own rank. This is enforced on the server, not just hidden in the UI. Ranks are configurable in **Pulse Settings**.

## AI control (MCP)

Pulse includes an MCP server so you can manage work by talking to Claude:

> *"Create a task in Operations: 'Prepare Q3 deck', high priority, assign bob@example.com, put it in To Do."*
> *"Move OPS-9 to In Progress and comment 'started'."*
> *"Add a sub-task 'write tests' under OPS-9."*

Setup (generate an API key, add to Claude Desktop / Code) is documented in **[`mcp/README.md`](mcp/README.md)**. The server exposes: `list_projects`, `list_tasks`, `get_task`, `list_sprints`, `list_users`, `create_task`, `update_task`, `move_task`, `assign_task`, `unassign_task`, `add_comment`, `add_subtask`, `add_dependency`, `delete_task`, `create_sprint`, `create_project`. All writes still pass Pulse's permission and hierarchy checks.

## Demo data

Populate every field of every doctype with realistic sample data (6 demo users, projects, tasks across all states, sprints, OKRs, risks, meetings, …):

```bash
bench --site your-site execute pulse.pulse.demo.showcase.run
# to remove it again:
bench --site your-site execute pulse.pulse.demo.showcase.clear
```

## Development

```bash
# backend: standard bench workflow
bench --site your-site migrate
bench start

# frontend: hot-reload dev server (proxies API to your bench)
cd apps/pulse/frontend
yarn install
yarn dev          # http://localhost:8080/pulse
yarn build        # production build into pulse/public/frontend
```

Project layout:

```
pulse/
├── frontend/                 # Vue 3 + frappe-ui SPA
│   └── src/{pages,components,ui,charts}
├── mcp/                      # MCP server for AI control
├── docs/                     # design docs (_canonical-model.md is the source of truth)
├── scripts/dev/              # throwaway dev/seed scripts
└── pulse/                    # the Frappe app
    ├── api/                  # pulse.api.*  (spa, dashboards, analytics, audit)
    ├── pulse/
    │   ├── doctype/          # ~50 Pulse doctypes
    │   ├── report/           # velocity, burndown, cumulative flow, …
    │   ├── demo/             # showcase seeder
    │   └── www/pulse.html    # serves the SPA at /pulse
    ├── hooks/                # doc-events, permissions, boot
    └── install.py            # roles, issue types, workflow, launcher, backfills
```

## Data model

Pulse owns ~50 doctypes, all prefixed `Pulse `, including: `Pulse Project`, `Pulse Task`, `Pulse Sprint`, `Pulse Issue Type`, `Pulse Task Status Log`, `Pulse Dependency`, `Pulse Checklist`, `Pulse Comment`, `Pulse Label`, `Pulse Dashboard` / `Pulse Dashboard Widget`, `Pulse Team`, `Pulse Portfolio`, `Pulse Objective` / `Pulse Key Result` / `Pulse OKR Check-in`, `Pulse Risk`, `Pulse Meeting`, `Pulse Change Request`, `Pulse Retrospective`, `Pulse Timesheet`, `Pulse Document`, `Pulse Holiday List`, `Pulse Settings`, and their child tables.

## Roadmap

- Gantt / timeline view with dependency arrows
- Milestones surfaced on board and timeline
- Board swimlanes & WIP limits
- Command palette (⌘K) global search
- Real drag-resize dashboard grid
- Real-time board updates (websocket)

## FAQ

**Does it need ERPNext?** No. Pulse is fully standalone and installs on a bare Frappe site.

**Where does the UI live?** A Vue SPA at `/pulse`. The old Desk pages have been retired — the SPA is the only UI.

**Are my tasks the same as ERPNext Tasks?** No — Pulse has its own `Pulse Task` doctype. Your data never leaks into another app.

**Can I use it without the frontend build step?** Yes — pre-built assets are committed. The build step is only for developing the UI.

## Contributing

Issues and PRs welcome. Please keep the standalone rule intact: **no Pulse doctype may link to a non-Pulse, non-framework doctype**, and no new dependency on ERPNext or any other app.

## License

[MIT](LICENSE)
