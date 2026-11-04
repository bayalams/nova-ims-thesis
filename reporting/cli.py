"""
Command-line interface for reporting recipes.
"""

import sys

from reporting.create_report import explain_report_recipe_text
from reporting.create_report import list_report_recipe_names
from reporting.create_report import print_report_status
from reporting.create_report import run_report_batch
from reporting.create_report import run_report_recipe
from reporting.context.source_registry import sort_report_batch_markdown
from reporting.evaluation import evaluate_report_run_folder
from reporting.html_viewer import write_report_batch_viewer
from reporting.strategies.context_construction import validate_context_strategy


def print_help():
    """
    Print available report commands.

    PARAMETERS:
    - None

    RETURNS:
    - None
    """
    print("Reporting commands:")
    print("  uv run report list-recipes")
    print("  uv run report status")
    print("  uv run report explain-recipe daily_tourism_intelligence")
    print("  uv run report run daily_tourism_intelligence --context-strategy simple")
    print("  uv run report run daily_tourism_intelligence --context-strategy simple --article-date 2026-04-10 --yes")
    print("  uv run report run daily_tourism_intelligence --context-strategy react-basic --knowledge-base-recipe news_recursive_2000_overlap_3large --article-date 2026-04-10 --yes")
    print("  uv run report run-batch daily_tourism_intelligence --article-date 2026-04-10 --run-name may10_check --strategy-delay-seconds 60 --yes")
    print("  uv run report evaluate-run shared_data/reports/may10_check")
    print("  uv run report render-viewer shared_data/reports/may10_check")
    print("  uv run report sort-batch shared_data/reports/may10_check")


def print_recipe_list():
    """
    Print every available report recipe.

    PARAMETERS:
    - None

    RETURNS:
    - None
    """
    recipe_names = list_report_recipe_names()
    print("[INFO] Report recipes")

    for position, recipe_name in enumerate(recipe_names, start=1):
        print(f"[{position}/{len(recipe_names)}] {recipe_name}")


def parse_run_arguments(arguments):
    """
    Parse arguments for the report run command.

    PARAMETERS:
    - arguments: The arguments after the word run

    RETURNS:
    - A dictionary with the parsed command choices
    """
    parsed = {
        "recipe_name": None,
        "context_strategy": None,
        "article_date": None,
        "report_datetime": None,
        "hours": None,
        "knowledge_base_recipe": None,
        "max_iterations": None,
        "candidate_limit": None,
        "yes": False,
    }

    position = 0

    while position < len(arguments):
        argument = arguments[position]

        if argument == "--yes":
            parsed["yes"] = True
            position = position + 1
            continue

        if argument.startswith("--"):
            if argument == "--context-strategy":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --context-strategy")
                parsed["context_strategy"] = validate_context_strategy(arguments[position + 1])
                position = position + 2
                continue

            if argument == "--article-date":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --article-date")
                parsed["article_date"] = arguments[position + 1]
                position = position + 2
                continue

            if argument == "--report-datetime":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --report-datetime")
                parsed["report_datetime"] = arguments[position + 1]
                position = position + 2
                continue

            if argument == "--hours":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --hours")
                parsed["hours"] = int(arguments[position + 1])
                position = position + 2
                continue

            if argument == "--knowledge-base-recipe":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --knowledge-base-recipe")
                parsed["knowledge_base_recipe"] = arguments[position + 1]
                position = position + 2
                continue

            if argument == "--max-iterations":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --max-iterations")
                parsed["max_iterations"] = int(arguments[position + 1])
                position = position + 2
                continue

            if argument == "--candidate-limit":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --candidate-limit")
                parsed["candidate_limit"] = int(arguments[position + 1])
                position = position + 2
                continue

            raise ValueError(f"Unknown report run option: {argument}")

        if parsed["recipe_name"] is None:
            parsed["recipe_name"] = argument
            position = position + 1
            continue

        raise ValueError(f"Unexpected report run argument: {argument}")

    if parsed["recipe_name"] is None:
        raise ValueError("Missing report recipe name")

    return parsed


def parse_run_batch_arguments(arguments):
    """
    Parse arguments for the report run-batch command.
    """
    parsed = {
        "recipe_name": None,
        "article_date": None,
        "report_datetime": None,
        "hours": None,
        "knowledge_base_recipe": None,
        "max_iterations": None,
        "candidate_limit": None,
        "run_name": None,
        "strategy_delay_seconds": None,
        "yes": False,
    }

    position = 0

    while position < len(arguments):
        argument = arguments[position]

        if argument == "--yes":
            parsed["yes"] = True
            position = position + 1
            continue

        if argument.startswith("--"):
            if argument == "--article-date":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --article-date")
                parsed["article_date"] = arguments[position + 1]
                position = position + 2
                continue

            if argument == "--report-datetime":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --report-datetime")
                parsed["report_datetime"] = arguments[position + 1]
                position = position + 2
                continue

            if argument == "--hours":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --hours")
                parsed["hours"] = int(arguments[position + 1])
                position = position + 2
                continue

            if argument == "--knowledge-base-recipe":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --knowledge-base-recipe")
                parsed["knowledge_base_recipe"] = arguments[position + 1]
                position = position + 2
                continue

            if argument == "--max-iterations":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --max-iterations")
                parsed["max_iterations"] = int(arguments[position + 1])
                position = position + 2
                continue

            if argument == "--candidate-limit":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --candidate-limit")
                parsed["candidate_limit"] = int(arguments[position + 1])
                position = position + 2
                continue

            if argument == "--run-name":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --run-name")
                parsed["run_name"] = arguments[position + 1]
                position = position + 2
                continue

            if argument == "--strategy-delay-seconds":
                if position + 1 >= len(arguments) or arguments[position + 1].startswith("--"):
                    raise ValueError("Missing value for --strategy-delay-seconds")
                parsed["strategy_delay_seconds"] = int(arguments[position + 1])
                position = position + 2
                continue

            raise ValueError(f"Unknown report run-batch option: {argument}")

        if parsed["recipe_name"] is None:
            parsed["recipe_name"] = argument
            position = position + 1
            continue

        raise ValueError(f"Unexpected report run-batch argument: {argument}")

    if parsed["recipe_name"] is None:
        raise ValueError("Missing report recipe name")

    return parsed


def main(arguments=None):
    """
    Run the reporting command-line interface.

    PARAMETERS:
    - arguments: Optional argument list for tests. If None, use sys.argv.

    RETURNS:
    - 0 when the command succeeds
    - 1 when the command fails
    """
    if arguments is None:
        arguments = sys.argv[1:]

    if len(arguments) == 0:
        print_help()
        return 0

    command = arguments[0]

    try:
        if command == "list-recipes":
            print_recipe_list()
            return 0

        if command == "status":
            print_report_status()
            return 0

        if command == "explain-recipe" and len(arguments) == 2:
            print(explain_report_recipe_text(arguments[1]))
            return 0

        if command == "run":
            parsed = parse_run_arguments(arguments[1:])
            run_report_recipe(
                parsed["recipe_name"],
                context_strategy=parsed["context_strategy"],
                article_date=parsed["article_date"],
                report_datetime=parsed["report_datetime"],
                hours=parsed["hours"],
                knowledge_base_recipe=parsed["knowledge_base_recipe"],
                max_iterations=parsed["max_iterations"],
                candidate_limit=parsed["candidate_limit"],
                yes=parsed["yes"],
            )
            return 0

        if command == "run-batch":
            parsed = parse_run_batch_arguments(arguments[1:])
            run_report_batch(
                parsed["recipe_name"],
                article_date=parsed["article_date"],
                report_datetime=parsed["report_datetime"],
                hours=parsed["hours"],
                knowledge_base_recipe=parsed["knowledge_base_recipe"],
                max_iterations=parsed["max_iterations"],
                candidate_limit=parsed["candidate_limit"],
                run_name=parsed["run_name"],
                strategy_delay_seconds=parsed["strategy_delay_seconds"],
                yes=parsed["yes"],
            )
            return 0

        if command == "render-viewer":
            if len(arguments) < 2:
                raise ValueError("Missing report run folder")
            if len(arguments) > 2:
                raise ValueError("Unexpected report render-viewer argument")
            viewer_path = write_report_batch_viewer(arguments[1])
            print(f"[INFO] Saved report viewer: {viewer_path}")
            return 0

        if command == "evaluate-run":
            if len(arguments) < 2:
                raise ValueError("Missing report run folder")
            if len(arguments) > 2:
                raise ValueError("Unexpected report evaluate-run argument")
            result = evaluate_report_run_folder(arguments[1])
            if result:
                print(f"[INFO] Saved report evaluation: {result['csv_path']}")
                print(f"[INFO] Saved report viewer: {result['viewer_path']}")
            return 0

        if command == "sort-batch":
            if len(arguments) < 2:
                raise ValueError("Missing report run folder")
            if len(arguments) > 2:
                raise ValueError("Unexpected report sort-batch argument")
            sort_report_batch_markdown(arguments[1])
            return 0
    except ValueError as error:
        print(f"[ERROR] {error}")
        return 1

    print(f"[ERROR] Unknown report command: {' '.join(arguments)}")
    print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
