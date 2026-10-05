from functools import lru_cache

import yaml

from .paths import CONFIG_DIR


@lru_cache(maxsize=1)
def load_settings() -> dict:
    with open(CONFIG_DIR / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
