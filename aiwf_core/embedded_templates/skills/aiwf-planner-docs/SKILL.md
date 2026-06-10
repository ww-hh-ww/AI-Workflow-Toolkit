---
name: aiwf-planner-docs
description: Project documentation writing guide — README and technical docs structure
---

# AIWF Planner — Documentation

Write or update project documentation after each task that changed module boundaries, public API, or subsystem behavior.

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

**When to write.** During the task, not after. Changed a subsystem -> update its doc. Section too long -> split to its own file. Two files always change together -> merge them. Structure grows with the code; don't pre-design it.
