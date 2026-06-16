---
name: aiwf-planner-docs
description: Project documentation writing guide — README and technical docs structure
---

# AIWF Planner — Documentation

Only write documentation when active plan Impact.docs=yes. If Impact.docs=no, do not invent documentation work. If Impact.docs=yes, update only the docs named by the plan or scope section.

This skill handles **growth documentation**: README and subsystem docs that
evolve with implementation. It is not the outlet for a whole-project final
architecture summary. When the user asks for a detailed architecture document,
or when milestone/release/handoff needs a system snapshot, use
`/aiwf-architecture-doc` instead.

**README.** First task: create `README.md` if it doesn't exist. Every task that changes project surface area: update it. Four things a stranger needs:

1. What this project is — one sentence about the problem it solves, not the tech stack.
2. How to run it — copy-paste commands that actually work. Clone, install, start.
3. What's inside — core capabilities, data flow, key technical choices. One paragraph each. No directory trees.
4. Where to look — point to `docs/` for details. README is the index, not the encyclopedia.

**Technical docs.** Create `docs/README.md` as the index. Each subsystem gets a section there, or its own file when the section grows too long. Each section needs five things:

1. What this subsystem does — one sentence.
2. Key functions and call chains — who calls whom, in what order.
3. Data flow — where data enters, how it moves, where it lands.
4. Edge cases — conditions that break, forbidden operations.
5. Pitfalls fixed — bugs already solved here and their root causes.

**When to write.** Controlled by active plan Impact.docs. Write during the task, not after. If Impact.docs=yes and the plan names specific docs, update those. Structure grows with the code; don't pre-design it.

**Where not to hide truth.** Durable structure belongs in PROJECT-MAP. A full
architecture snapshot belongs in `.aiwf/artifacts/reports/架构详细设计.md`.
Do not scatter summary architecture knowledge only across README, closure
reports, review comments, or session memory.
