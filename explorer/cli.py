"""
Command-line interface for exploratory work.
"""

from pathlib import Path
import sys


def print_help():
    """
    Print available explorer commands.
    """
    print("[INFO] Explorer")
    print("Use this folder to inspect data, compare methods, and sanity-check outputs.")
    print("")
    print("[INFO] Available commands")
    print(
        "  corpus-inspector index [--raw-dir PATH] [--clean-dir PATH] "
        "[--index-path PATH] [--minimum-text-characters N]"
    )
    print("  corpus-inspector status [--index-path PATH]")
    print("  corpus-inspector serve [--index-path PATH] [--host HOST] [--port PORT]")
    print("  kb-observatory serve [--kb-root PATH] [--evaluation-path PATH] [--host HOST] [--port PORT]")


def parse_required_value(arguments, index, option_name):
    """
    Return the value after an option, or raise a plain error.
    """
    if index + 1 >= len(arguments):
        raise ValueError("Missing value for " + option_name)

    return arguments[index + 1]


def parse_corpus_index_arguments(arguments):
    """
    Parse corpus inspector index options.
    """
    options = {
        "raw_dir": None,
        "clean_dir": None,
        "index_path": None,
        "minimum_text_characters": None,
    }

    index = 0
    while index < len(arguments):
        option_name = arguments[index]

        if option_name == "--raw-dir":
            value = parse_required_value(arguments, index, option_name)
            options["raw_dir"] = Path(value)
            index = index + 2
        elif option_name == "--clean-dir":
            value = parse_required_value(arguments, index, option_name)
            options["clean_dir"] = Path(value)
            index = index + 2
        elif option_name == "--index-path":
            value = parse_required_value(arguments, index, option_name)
            options["index_path"] = Path(value)
            index = index + 2
        elif option_name == "--minimum-text-characters":
            value = parse_required_value(arguments, index, option_name)
            try:
                options["minimum_text_characters"] = int(value)
            except ValueError:
                raise ValueError("Invalid integer for " + option_name)
            index = index + 2
        else:
            raise ValueError("Unknown corpus-inspector index option: " + option_name)

    return options


def parse_corpus_serve_arguments(arguments):
    """
    Parse corpus inspector serve options.
    """
    options = {
        "index_path": None,
        "host": None,
        "port": None,
    }

    index = 0
    while index < len(arguments):
        option_name = arguments[index]

        if option_name == "--index-path":
            value = parse_required_value(arguments, index, option_name)
            options["index_path"] = Path(value)
            index = index + 2
        elif option_name == "--host":
            value = parse_required_value(arguments, index, option_name)
            options["host"] = value
            index = index + 2
        elif option_name == "--port":
            value = parse_required_value(arguments, index, option_name)
            try:
                options["port"] = int(value)
            except ValueError:
                raise ValueError("Invalid integer for " + option_name)
            index = index + 2
        else:
            raise ValueError("Unknown corpus-inspector serve option: " + option_name)

    return options


def parse_kb_observatory_serve_arguments(arguments):
    """
    Parse KB Observatory serve options.
    """
    options = {
        "kb_root": None,
        "evaluation_path": None,
        "host": None,
        "port": None,
    }

    index = 0
    while index < len(arguments):
        option_name = arguments[index]

        if option_name == "--kb-root":
            value = parse_required_value(arguments, index, option_name)
            options["kb_root"] = Path(value)
            index = index + 2
        elif option_name == "--evaluation-path":
            value = parse_required_value(arguments, index, option_name)
            options["evaluation_path"] = Path(value)
            index = index + 2
        elif option_name == "--host":
            value = parse_required_value(arguments, index, option_name)
            options["host"] = value
            index = index + 2
        elif option_name == "--port":
            value = parse_required_value(arguments, index, option_name)
            try:
                options["port"] = int(value)
            except ValueError:
                raise ValueError("Invalid integer for " + option_name)
            index = index + 2
        else:
            raise ValueError("Unknown kb-observatory serve option: " + option_name)

    return options


def parse_corpus_status_arguments(arguments):
    """
    Parse corpus inspector status options.
    """
    options = {
        "index_path": None,
    }

    index = 0
    while index < len(arguments):
        option_name = arguments[index]

        if option_name == "--index-path":
            value = parse_required_value(arguments, index, option_name)
            options["index_path"] = Path(value)
            index = index + 2
        else:
            raise ValueError("Unknown corpus-inspector status option: " + option_name)

    return options


def make_kwargs(options):
    """
    Return keyword arguments, skipping values that should use defaults.
    """
    kwargs = {}

    for key in options:
        if options[key] is not None:
            kwargs[key] = options[key]

    return kwargs


def run_corpus_inspector(arguments):
    """
    Route corpus inspector commands.
    """
    from explorer.webapps.corpus_inspector.indexer import build_corpus_index
    from explorer.webapps.corpus_inspector.indexer import get_index_status

    if len(arguments) == 0:
        print("[ERROR] Missing corpus-inspector command")
        return 1

    command = arguments[0]

    try:
        if command == "index":
            options = parse_corpus_index_arguments(arguments[1:])
            kwargs = make_kwargs(options)
            result = build_corpus_index(**kwargs)
            print("[INFO] Corpus inspector index ready: " + result["index_path"])
            print("[INFO] Indexed articles: " + str(result["article_count"]))
            return 0

        if command == "status":
            options = parse_corpus_status_arguments(arguments[1:])
            kwargs = make_kwargs(options)
            result = get_index_status(**kwargs)
            print("[INFO] Corpus inspector index: " + result["index_path"])
            print("[INFO] Exists: " + str(result["exists"]))
            if "article_count" in result:
                print("[INFO] Indexed articles: " + str(result["article_count"]))
            return 0

        if command == "serve":
            from explorer.webapps.corpus_inspector.server import serve_corpus_inspector

            options = parse_corpus_serve_arguments(arguments[1:])
            kwargs = make_kwargs(options)
            return serve_corpus_inspector(**kwargs)
    except ValueError as error:
        print("[ERROR] " + str(error))
        return 1

    print("[ERROR] Unknown corpus-inspector command: " + command)
    return 1


def run_kb_observatory(arguments):
    """
    Route KB Observatory commands.
    """
    if len(arguments) == 0:
        print("[ERROR] Missing kb-observatory command")
        return 1

    command = arguments[0]

    try:
        if command == "serve":
            from explorer.webapps.kb_observatory.server import serve_kb_observatory

            options = parse_kb_observatory_serve_arguments(arguments[1:])
            kwargs = make_kwargs(options)
            return serve_kb_observatory(**kwargs)
    except ValueError as error:
        print("[ERROR] " + str(error))
        return 1

    print("[ERROR] Unknown kb-observatory command: " + command)
    return 1


def main(arguments=None):
    """
    Route explorer commands.
    """
    if arguments is None:
        arguments = sys.argv[1:]

    if len(arguments) == 0:
        print_help()
        return 0

    command = arguments[0]

    if command == "corpus-inspector":
        return run_corpus_inspector(arguments[1:])

    if command == "kb-observatory":
        return run_kb_observatory(arguments[1:])

    print("[ERROR] Unknown explorer command: " + command)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
