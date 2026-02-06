"""
CalSci Flasher - Utility Functions Module
Contains helper functions for file operations, git management, and device detection.
"""

import json
import shutil
from pathlib import Path
from serial.tools import list_ports
import git

from config import ROOT, SELECTIONS_FILE, ESP32_KEYWORDS, REPO_URL, BRANCH


# ================= SELECTION MEMORY MANAGER =================

class SelectionMemory:
    """Manages persistent storage of file selections"""

    @staticmethod
    def save_selections(selected_paths):
        try:
            paths_to_save = [str(p) for p in selected_paths]
            with open(SELECTIONS_FILE, 'w') as f:
                json.dump(paths_to_save, f, indent=2)
        except Exception as e:
            print(f"Error saving selections: {e}")

    @staticmethod
    def load_selections():
        try:
            if SELECTIONS_FILE.exists():
                with open(SELECTIONS_FILE, 'r') as f:
                    paths = json.load(f)
                    return [Path(p) for p in paths if Path(p).exists()]
        except Exception as e:
            print(f"Error loading selections: {e}")
        return []

    @staticmethod
    def clear_selections():
        try:
            if SELECTIONS_FILE.exists():
                SELECTIONS_FILE.unlink()
        except Exception as e:
            print(f"Error clearing selections: {e}")

    @staticmethod
    def has_selections():
        return SELECTIONS_FILE.exists() and SELECTIONS_FILE.stat().st_size > 0


# ================= ESP32 PORT DETECTION =================

def find_esp32_ports():
    """Detect connected ESP32 devices."""
    ports = []
    for p in list_ports.comports():
        text = f"{p.manufacturer} {p.description}".lower()
        if any(k.lower() in text for k in ESP32_KEYWORDS):
            ports.append(p.device)
    return ports


# ================= GIT HELPERS =================

def ensure_repo(log_func):
    """Clone repository if it doesn't exist."""
    if not ROOT.exists():
        log_func("Cloning repository...", "info")
        git.Repo.clone_from(REPO_URL, ROOT, branch=BRANCH)
        log_func("Repository cloned successfully", "success")
    else:
        log_func("Repository found", "info")


def delete_repo(log_func):
    """Delete the local repository if it exists."""
    if ROOT.exists():
        log_func("Deleting existing repository...", "info")
        shutil.rmtree(ROOT)
        log_func("Repository deleted", "success")
    else:
        log_func("No existing repository to delete", "info")


def repo_status(log_func):
    """Check repository status (ahead/behind)."""
    repo = git.Repo(ROOT)
    repo.remotes.origin.fetch()
    behind = sum(1 for _ in repo.iter_commits(f"{BRANCH}..origin/{BRANCH}"))
    ahead = sum(1 for _ in repo.iter_commits(f"origin/{BRANCH}..{BRANCH}"))
    return ahead, behind


def pull_repo(log_func):
    """Pull latest changes from repository."""
    repo = git.Repo(ROOT)
    repo.remotes.origin.pull()
    log_func("Repository updated", "success")


# ================= FILE FILTER =================

def should_skip(path: Path) -> bool:
    """Check if a file should be skipped during upload."""
    if any(part.startswith(".") for part in path.parts):
        return True
    if path.name in {".gitignore", ".gitattributes"}:
        return True
    if path.suffix == ".pyc":
        return True
    return False


def get_all_files(root_path):
    """Get all files from the root path, scanning fresh from disk each time."""
    return [p for p in root_path.rglob("*") if p.is_file() and not should_skip(p)]


def get_main_file_after_all_clean():
    pass