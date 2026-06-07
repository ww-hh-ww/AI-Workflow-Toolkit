"""Workflow recipe command handlers."""
from __future__ import annotations

import argparse
import sys


def _cmd_recipe_list(args: argparse.Namespace) -> None:
    from ..core.workflow_recipes import get_recipe, list_recipes
    print("Workflow recipes:")
    for name in list_recipes():
        recipe = get_recipe(name)
        print(f"  - {name}: {recipe['description']}")


def _cmd_recipe_show(args: argparse.Namespace) -> None:
    from ..core.workflow_recipes import get_recipe
    try:
        recipe = get_recipe(args.name)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"# {args.name}")
    print(recipe["description"])
    print(f"  request_mode: {recipe['request_mode']}")
    print(f"  workflow_pattern: {recipe['workflow_pattern']}")
    print(f"  minimum_level: {recipe['minimum_level']}")
    print("  Advisory only: applying a recipe still requires explicit AIWF state operations.")
    for key in ["required_contract_fields", "test_focus", "review_focus", "escalation_triggers"]:
        print(f"  {key}:")
        for item in recipe.get(key, []):
            print(f"    - {item}")


def _cmd_recipe_recommend(args: argparse.Namespace) -> None:
    from ..core.workflow_recipes import recommend_recipes
    recipes = recommend_recipes(task_type=args.task_type or "", risk_flags=args.risk_flags or [])
    print(f"Recommended recipes: {len(recipes)}")
    for recipe in recipes:
        print(f"  - {recipe['name']} ({recipe['workflow_pattern']}, min={recipe['minimum_level']})")
        print(f"    {recipe['description']}")
    print("  Advisory only: applying a recipe still requires explicit AIWF state operations.")


def _cmd_recipe_help(args: argparse.Namespace) -> None:
    print("AIWF Workflow Recipes")
    print()
    print("Available subcommands:")
    print("  aiwf recipe list       — list recipes")
    print("  aiwf recipe show NAME  — show one recipe")
    print("  aiwf recipe recommend  — recommend recipes from task type/risk flags")
