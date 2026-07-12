# Code Reality Review

Use this when the selected lens is `code-reality`.

Read code to test the mission claim. Do not review only changed lines.

## Main Path

Ask:

- What path actually delivers the reviewed capability?
- Who calls it?
- Is the new capability consumed there?
- Does an old path still bypass it?
- Are two mechanisms now doing the same job?

For zero-caller code, decide which case it is:

- abandoned old code: cleanup candidate;
- new but unwired code: bug.

## Public Reality

Check the governed project's public surfaces:

- commands;
- help text;
- templates;
- docs;
- user entry points;
- deployment or integration scripts.

They must point to the real main path. If they describe an old path or a path
that is not wired, report it.

## Structure

Ask:

- Are module responsibilities clear?
- Are abstractions carrying their weight?
- Are data flow and control flow easy to follow?
- Did implementation introduce a design decision that planning docs do not
  mention?
- Does duplicated or unwired code show the design has split into competing
  paths?
