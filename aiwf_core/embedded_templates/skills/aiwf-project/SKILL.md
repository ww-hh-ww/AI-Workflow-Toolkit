---
name: aiwf-project
description: Project-specific knowledge, rules, and workflows. Loaded before every AIWF skill.
---

# AIWF Project

This file is yours. Put project-specific knowledge here that every AIWF
skill should know before it starts. The AIWF framework loads this first.

## What goes here

- **Operations**: how to build, test, deploy, sync VMs. Save subagents from
  re-discovering what you already know.
- **Known conclusions**: dead ends you've already explored, architectural
  decisions, dependency constraints. Prevent wasted re-exploration.
- **Dispatch rules**: which changes always/never need tester or reviewer.
  Tune the framework to your project's risk profile.

## How it works

Every AIWF skill loads this file as its first step. You write the rules;
the framework enforces them.
