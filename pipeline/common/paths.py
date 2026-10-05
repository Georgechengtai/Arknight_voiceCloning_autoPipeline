"""專案內的固定路徑。全部相對於倉庫根目錄（pipeline/ 的上兩層）。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
GAMEDATA_DIR = ROOT / "data" / "gamedata"
EXCEL_DIR = GAMEDATA_DIR / "excel"
STORY_DIR = GAMEDATA_DIR / "story"
OUT_DIR = ROOT / "out"
SCHEMA_DIR = ROOT / "pipeline" / "schemas"
ASSETS_DIR = ROOT / "assets"
CACHE_DIR = ROOT / "cache"
