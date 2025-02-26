import json
import os
from typing import Any

CONFIG_FILE: str = os.path.join(
    os.path.expanduser("~"), ".youtube_downloader_config.json"
)
DEFAULT_CONFIG: dict[str, Any] = {
    "download_folder": os.path.join(os.path.expanduser("~"), "Downloads")
}


def load_config() -> dict[str, Any]:
    """Load configuration from file.

    Returns:
        dict[str, Any]: Configuration dictionary.
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        except Exception:
            config = DEFAULT_CONFIG.copy()
    else:
        config = DEFAULT_CONFIG.copy()
    return config


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to file.

    Args:
        config (dict[str, Any]): Configuration dictionary to save.
    """
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print("Error saving config:", e)
