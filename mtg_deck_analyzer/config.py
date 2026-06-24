"""Loads optional configuration from a TOML file.

Recognized top-level keys:
    api_key = "your_gemini_api_key"   # Google Gemini API key
    lang    = "it"                    # default target language code

Lookup order when no explicit path is given:
    1. ./config.toml (current working directory)
    2. config.toml next to the project root
"""

import os
import tomllib

CONFIG_FILENAME = "config.toml"


def _candidate_paths(explicit_path: str = None) -> list:
    if explicit_path:
        return [explicit_path]

    package_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(package_dir)
    return [
        os.path.join(os.getcwd(), CONFIG_FILENAME),
        os.path.join(project_dir, CONFIG_FILENAME),
    ]


def load_config(explicit_path: str = None) -> dict:
    """Returns the parsed config (keys: api_key, lang) or {} if no file is found.

    If an explicit path is given but does not exist, a warning is printed.
    """
    for path in _candidate_paths(explicit_path):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            print(f"[Warning] Failed to read config file '{path}': {e}")
            return {}
        return {
            "api_key": data.get("api_key"),
            "lang": data.get("lang"),
            "path": path,
        }

    if explicit_path:
        print(f"[Warning] Config file not found at '{explicit_path}'.")
    return {}
