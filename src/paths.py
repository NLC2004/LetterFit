from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DRAFTS_DIR = ROOT / "drafts"
ATTACHMENTS_DIR = ROOT / "attachments"
TEMPLATE_DIR = ROOT / "Template"
TEMPLATE_FILE = TEMPLATE_DIR / "template"
ENV_FILE = ROOT / ".env"

PROFILE_FILE = CONFIG_DIR / "profile.yaml"
SCHOOLS_FILE = CONFIG_DIR / "schools.yaml"
SETTINGS_FILE = CONFIG_DIR / "settings.yaml"
TARGETS_FILE = DATA_DIR / "targets.csv"
SENT_LOG_FILE = DATA_DIR / "sent_log.jsonl"
LOG_DIR = ROOT / "logs"
