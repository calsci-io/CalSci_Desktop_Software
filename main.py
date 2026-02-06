"""
CalSci Flasher - Main Application
CalSci MicroPython file flasher with Git repository sync.
"""

import sys
<<<<<<< HEAD
import time
import threading
import json
from pathlib import Path
from queue import Queue, Empty
from collections import deque

import git
from serial.tools import list_ports
import serial

import pygame
from pygame import gfxdraw

# ================= CONFIG =================

REPO_URL = "https://github.com/calsci-io/calsci_latest_itr"
BRANCH = "main"
ROOT = Path("./calsci_latest_itr")
SELECTIONS_FILE = Path("./upload_selections.json")

ESP32_KEYWORDS = ("Espressif",)
BAUDRATE = 115200
REPL_DELAY = 0.1

# ================= SELECTION MEMORY MANAGER =================

class SelectionMemory:
    """Manages persistent storage of file selections"""
    
    @staticmethod
    def save_selections(selected_paths):
        """Save selected file paths to JSON file"""
        try:
            paths_to_save = [str(p) for p in selected_paths]
            with open(SELECTIONS_FILE, 'w') as f:
                json.dump(paths_to_save, f, indent=2)
            print(f"Saved {len(paths_to_save)} selections to {SELECTIONS_FILE}")
        except Exception as e:
            print(f"Error saving selections: {e}")
    
    @staticmethod
    def load_selections():
        """Load previously selected file paths from JSON file"""
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
        """Clear saved selections"""
        try:
            if SELECTIONS_FILE.exists():
                SELECTIONS_FILE.unlink()
                print(f"Cleared selections from {SELECTIONS_FILE}")
        except Exception as e:
            print(f"Error clearing selections: {e}")
    
    @staticmethod
    def has_selections():
        """Check if there are saved selections"""
        return SELECTIONS_FILE.exists() and SELECTIONS_FILE.stat().st_size > 0

# ================= LINUX-STYLE COLORS =================

class Colors:
    BG = (45, 45, 45)
    SIDEBAR = (35, 35, 35)
    HEADER = (30, 30, 30)
    CARD = (50, 50, 50)
    
    ACCENT = (233, 84, 32)
    ACCENT_HOVER = (253, 104, 52)
    ACCENT_DARK = (213, 64, 12)
    
    SUCCESS = (119, 178, 85)
    ERROR = (235, 77, 75)
    WARNING = (242, 169, 59)
    
    TEXT = (240, 240, 240)
    TEXT_DIM = (160, 160, 160)
    TEXT_DISABLED = (100, 100, 100)
    
    BORDER = (70, 70, 70)
    HOVER = (60, 60, 60)
    SELECTED = (55, 55, 65)
    
    PROGRESS_BG = (40, 40, 40)
    PROGRESS_TRACK = (25, 25, 25)

# =========================================

# ---------- ESP32 PORT DETECTION ----------

def find_esp32_ports():
    ports = []
    for p in list_ports.comports():
        text = f"{p.manufacturer} {p.description}".lower()
        if any(k.lower() in text for k in ESP32_KEYWORDS):
            ports.append(p.device)
    return ports

# ---------- GIT HELPERS ----------

def ensure_repo(log_func):
    if not ROOT.exists():
        log_func(f"Cloning repository...", "info")
        git.Repo.clone_from(REPO_URL, ROOT, branch=BRANCH)
        log_func("Repository cloned successfully", "success")
    else:
        log_func("Repository found", "info")

def repo_status(log_func):
    repo = git.Repo(ROOT)
    repo.remotes.origin.fetch()
    
    behind = sum(1 for _ in repo.iter_commits(f"{BRANCH}..origin/{BRANCH}"))
    ahead = sum(1 for _ in repo.iter_commits(f"origin/{BRANCH}..{BRANCH}"))
    
    return ahead, behind

def pull_repo(log_func):
    repo = git.Repo(ROOT)
    repo.remotes.origin.pull()
    log_func("Repository updated", "success")

# ---------- FILE FILTER ----------

def should_skip(path: Path) -> bool:
    if any(part.startswith(".") for part in path.parts):
        return True
    if path.name in {".gitignore", ".gitattributes"}:
        return True
    if path.suffix == ".pyc":
        return True
    return False

# ============================================================
# ================= FILE TREE (LINUX STYLE) ==================
# ============================================================

class TreeNode:
    def __init__(self, path, is_folder=False, parent=None):
        self.path = path
        self.name = path.name if path else "ROOT"
        self.is_folder = is_folder
        self.parent = parent
        self.children = []
        self.expanded = False
        self.selected = False
        self.file_path = None
        self._calculate_depth()
    
    def _calculate_depth(self):
        depth = 0
        node = self.parent
        while node:
            depth += 1
            node = node.parent
        self.depth = depth
    
    def toggle_expand(self):
        if self.is_folder:
            self.expanded = not self.expanded
    
    def toggle_select(self):
        self.selected = not self.selected
        if self.is_folder:
            for child in self.children:
                child._set_selection_recursive(self.selected)
    
    def _set_selection_recursive(self, selected):
        self.selected = selected
        for child in self.children:
            child._set_selection_recursive(selected)
    
    def get_all_files(self):
        files = []
        if not self.is_folder and self.selected and self.file_path:
            files.append(self.file_path)
        for child in self.children:
            files.extend(child.get_all_files())
        return files


class FileTreeView:
    """Linux-style file tree with clean flat design"""
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.root = None
        self.visible_nodes = []
        
        self.scroll_offset = 0.0
        self.target_scroll = 0.0
        self.scroll_velocity = 0.0
        self.max_scroll = 0
        
        self.font = pygame.font.Font(None, 20)
        self.icon_font = pygame.font.Font(None, 18)
        self.row_height = 24
        self.indent = 20
        self.checkbox_size = 16
        self.hover_index = -1
    
    def build_tree(self, root_path, all_files, pre_selected_files=None):
        self.root = TreeNode(root_path, is_folder=True)
        self.root.expanded = True
        folder_map = {str(root_path): self.root}
        
        pre_selected_set = set()
        if pre_selected_files:
            for p in pre_selected_files:
                if isinstance(p, Path):
                    pre_selected_set.add(str(p))
                else:
                    pre_selected_set.add(str(Path(p)))
        
        file_dirs = set()
        for file_path in all_files:
            rel_path = file_path.relative_to(root_path)
            for parent in rel_path.parents:
                dir_path = root_path / parent
                file_dirs.add(dir_path)
        
        sorted_dirs = sorted(file_dirs, key=lambda d: len(str(d)))
        
        for dir_path in sorted_dirs:
            rel_parts = dir_path.relative_to(root_path).parts
            current_path = root_path
            parent_node = self.root
            
            for part in rel_parts:
                current_path = current_path / part
                folder_key = str(current_path)
                
                if folder_key not in folder_map:
                    new_node = TreeNode(current_path, is_folder=True, parent=parent_node)
                    parent_node.children.append(new_node)
                    folder_map[folder_key] = new_node
                
                parent_node = folder_map[folder_key]
        
        for file_path in sorted(all_files, key=lambda p: str(p)):
            parts = file_path.relative_to(root_path).parts
            current_path = root_path
            parent_node = self.root
            
            for part in parts[:-1]:
                current_path = current_path / part
                folder_key = str(current_path)
                if folder_key in folder_map:
                    parent_node = folder_map[folder_key]
            
            file_node = TreeNode(file_path, is_folder=False, parent=parent_node)
            file_node.file_path = file_path
            
            if str(file_path) in pre_selected_set:
                file_node.selected = True
            
            parent_node.children.append(file_node)
        
        def sort_children(node):
            node.children.sort(key=lambda n: (0 if n.is_folder else 1, n.name.lower()))
            for child in node.children:
                if child.is_folder:
                    sort_children(child)
        
        sort_children(self.root)
        self._update_visible_nodes()
    
    def _update_visible_nodes(self):
        self.visible_nodes = []
        
        def add_node(node):
            self.visible_nodes.append(node)
            if node.is_folder and node.expanded:
                for child in node.children:
                    add_node(child)
        
        if self.root:
            for child in self.root.children:
                add_node(child)
        
        total_height = len(self.visible_nodes) * self.row_height
        self.max_scroll = max(0, total_height - self.height)
        
        self.target_scroll = max(0, min(self.target_scroll, self.max_scroll))
        self.scroll_offset = max(0, min(self.scroll_offset, self.max_scroll))
    
    def update(self):
        if abs(self.scroll_offset - self.target_scroll) > 0.5:
            distance = self.target_scroll - self.scroll_offset
            self.scroll_offset += distance * 0.22
            self.scroll_offset = max(0, min(self.scroll_offset, self.max_scroll))
        else:
            self.scroll_offset = self.target_scroll
            self.scroll_velocity = 0.0
    
    def draw(self, screen):
        pygame.draw.rect(screen, Colors.CARD, (self.x, self.y, self.width, self.height))
        pygame.draw.rect(screen, Colors.BORDER, (self.x, self.y, self.width, self.height), 1)
        
        clip_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        screen.set_clip(clip_rect)
        
        y = self.y - int(self.scroll_offset)
        
        for idx, node in enumerate(self.visible_nodes):
            if y + self.row_height < self.y:
                y += self.row_height
                continue
            if y > self.y + self.height:
                break
            
            row_rect = pygame.Rect(self.x, y, self.width, self.row_height)
            if idx == self.hover_index:
                pygame.draw.rect(screen, Colors.HOVER, row_rect)
            
            if node.selected:
                pygame.draw.rect(screen, Colors.SELECTED, row_rect)
            
            x_offset = self.x + 8 + (node.depth * self.indent)
            
            checkbox_rect = pygame.Rect(x_offset, y + 4, self.checkbox_size, self.checkbox_size)
            pygame.draw.rect(screen, Colors.BORDER, checkbox_rect, 1)
            
            if node.selected:
                check_color = Colors.ACCENT
                pygame.draw.rect(screen, check_color, checkbox_rect.inflate(-2, -2))
                check_surf = self.icon_font.render("✓", True, Colors.TEXT)
                screen.blit(check_surf, (x_offset + 2, y + 2))
            
            x_offset += self.checkbox_size + 8
            
            if node.is_folder:
                icon = "📁"
                color = Colors.ACCENT
            else:
                ext = node.path.suffix
                if ext in ['.py']:
                    icon = "🐍"
                elif ext in ['.txt', '.md']:
                    icon = "📄"
                elif ext in ['.json', '.xml', '.yaml']:
                    icon = "⚙"
                else:
                    icon = "📄"
                color = Colors.TEXT_DIM
            
            icon_surf = self.icon_font.render(icon, True, color)
            screen.blit(icon_surf, (x_offset, y + 3))
            x_offset += 20
            
            name_color = Colors.TEXT if not node.is_folder else Colors.TEXT
            name_surf = self.font.render(node.name, True, name_color)
            screen.blit(name_surf, (x_offset, y + 4))
            
            y += self.row_height
        
        screen.set_clip(None)
        
        total_height = len(self.visible_nodes) * self.row_height
        if total_height > self.height:
            scrollbar_width = 8
            scrollbar_height = max(30, int(self.height * self.height / total_height))
            
            scroll_ratio = self.scroll_offset / self.max_scroll if self.max_scroll > 0 else 0
            scrollbar_y = self.y + int(scroll_ratio * (self.height - scrollbar_height))
            
            track_rect = pygame.Rect(self.x + self.width - scrollbar_width - 2, self.y + 2, 
                                    scrollbar_width, self.height - 4)
            pygame.draw.rect(screen, Colors.PROGRESS_TRACK, track_rect, border_radius=4)
            
            thumb_rect = pygame.Rect(self.x + self.width - scrollbar_width - 2, scrollbar_y,
                                    scrollbar_width, scrollbar_height)
            pygame.draw.rect(screen, Colors.ACCENT, thumb_rect, border_radius=4)
    
    def handle_click(self, pos):
        if not (self.x <= pos[0] <= self.x + self.width and
                self.y <= pos[1] <= self.y + self.height):
            return

        y = self.y - int(self.scroll_offset)
        for node in self.visible_nodes:
            if y <= pos[1] < y + self.row_height:
                x_offset = self.x + 8 + (node.depth * self.indent)

                if node.is_folder and pos[0] < x_offset + 16:
                    node.toggle_expand()
                    self._update_visible_nodes()
                elif pos[0] >= x_offset + 16 and pos[0] < x_offset + 16 + self.checkbox_size + 8:
                    node.toggle_select()
                elif node.is_folder:
                    node.toggle_expand()
                    self._update_visible_nodes()
                else:
                    node.toggle_select()
                return

            y += self.row_height
    
    def handle_motion(self, pos):
        if not (self.x <= pos[0] <= self.x + self.width and 
                self.y <= pos[1] <= self.y + self.height):
            self.hover_index = -1
            return
        
        y = self.y - int(self.scroll_offset)
        for idx, node in enumerate(self.visible_nodes):
            if y <= pos[1] < y + self.row_height:
                self.hover_index = idx
                return
            y += self.row_height
        self.hover_index = -1
    
    def handle_scroll(self, delta):
        self.target_scroll = max(0, min(self.target_scroll + delta, self.max_scroll))
    
    def select_all(self):
        if self.root:
            for child in self.root.children:
                child._set_selection_recursive(True)
    
    def deselect_all(self):
        if self.root:
            for child in self.root.children:
                child._set_selection_recursive(False)
    
    def get_selected_files(self):
        if self.root:
            return self.root.get_all_files()
        return []


# ============================================================
# ================= LINUX-STYLE DIALOG =======================
# ============================================================

class FileSelectionDialog:
    """Linux-style modal dialog"""
    def __init__(self, screen, all_files, root_path, pre_selected_files=None):
        self.screen = screen
        self.width = 700
        self.height = 500
        self.x = (800 - self.width) // 2
        self.y = (600 - self.height) // 2
        
        self.header_height = 50
        
        tree_y = self.y + self.header_height + 50
        self.tree = FileTreeView(
            self.x + 10,
            tree_y,
            self.width - 20,
            self.height - self.header_height - 120
        )
        self.tree.build_tree(root_path, all_files, pre_selected_files)
        
        button_y = self.y + self.height - 50
        button_width = 120
        button_height = 35
        spacing = 10
        
        total_button_width = button_width * 4 + spacing * 3
        start_x = self.x + (self.width - total_button_width) // 2
        
        self.select_all_btn = LinuxButton(
            start_x, button_y, button_width, button_height, "Select All"
        )
        
        self.deselect_all_btn = LinuxButton(
            start_x + button_width + spacing, button_y, button_width, button_height, "Deselect All"
        )
        
        self.upload_btn = LinuxButton(
            start_x + (button_width + spacing) * 2, button_y, button_width, button_height, "Upload", primary=True
        )
        
        self.cancel_btn = LinuxButton(
            start_x + (button_width + spacing) * 3, button_y, button_width, button_height, "Cancel"
        )
        
        self.title_font = pygame.font.Font(None, 28)
        self.font = pygame.font.Font(None, 20)
        self.result = None
    
    def update(self):
        self.tree.update()
    
    def draw(self):
        overlay = pygame.Surface((800, 600), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        
        pygame.draw.rect(self.screen, Colors.CARD, (self.x, self.y, self.width, self.height))
        pygame.draw.rect(self.screen, Colors.BORDER, (self.x, self.y, self.width, self.height), 1)
        
        header_rect = pygame.Rect(self.x, self.y, self.width, self.header_height)
        pygame.draw.rect(self.screen, Colors.HEADER, header_rect)
        pygame.draw.line(self.screen, Colors.BORDER, 
                        (self.x, self.y + self.header_height),
                        (self.x + self.width, self.y + self.header_height))
        
        title_surf = self.title_font.render("Select Files to Upload", True, Colors.TEXT)
        title_rect = title_surf.get_rect(midleft=(self.x + 20, self.y + self.header_height // 2))
        self.screen.blit(title_surf, title_rect)
        
        selected_count = len(self.tree.get_selected_files())
        total_files = sum(1 for node in self.tree.visible_nodes if not node.is_folder)
        
        count_text = f"{selected_count} / {total_files} selected"
        count_surf = self.font.render(count_text, True, Colors.TEXT_DIM)
        count_rect = count_surf.get_rect(center=(self.x + self.width // 2, 
                                                  self.y + self.header_height + 25))
        self.screen.blit(count_surf, count_rect)
        
        if SelectionMemory.has_selections():
            memory_text = " "
            memory_surf = self.font.render(memory_text, True, Colors.ACCENT)
            memory_rect = memory_surf.get_rect(midright=(self.x + self.width - 20,
                                                         self.y + self.header_height + 25))
            self.screen.blit(memory_surf, memory_rect)
        
        self.tree.draw(self.screen)
        
        self.select_all_btn.draw(self.screen)
        self.deselect_all_btn.draw(self.screen)
        
        if selected_count > 0:
            self.upload_btn.text = f"Upload ({selected_count})"
        else:
            self.upload_btn.text = "Upload"
        
        self.upload_btn.draw(self.screen)
        self.cancel_btn.draw(self.screen)
    
    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self.select_all_btn.handle_click(event.pos):
                    self.tree.select_all()
                elif self.deselect_all_btn.handle_click(event.pos):
                    self.tree.deselect_all()
                elif self.upload_btn.handle_click(event.pos):
                    self.result = "upload"
                elif self.cancel_btn.handle_click(event.pos):
                    self.result = "cancel"
                else:
                    self.tree.handle_click(event.pos)
            elif event.button == 4:
                self.tree.handle_scroll(-40)
            elif event.button == 5:
                self.tree.handle_scroll(40)
        
        if event.type == pygame.MOUSEMOTION:
            self.select_all_btn.handle_motion(event.pos)
            self.deselect_all_btn.handle_motion(event.pos)
            self.upload_btn.handle_motion(event.pos)
            self.cancel_btn.handle_motion(event.pos)
            self.tree.handle_motion(event.pos)
    
    def get_selected_files(self):
        return self.tree.get_selected_files()


# ============================================================
# ================= MICRO-PY FLASHER =========================
# ============================================================

class MicroPyError(Exception):
    pass

class MicroPyFlasher:
    def __init__(self, port, baudrate=BAUDRATE):
        self.port = port
        self.ser = serial.Serial(port, baudrate, timeout=0.1)
        self._wait_ready(2.0)
        self._enter_repl()
    
    def close(self):
        self.ser.close()
    
    def _wait_ready(self, duration):
        end_time = time.perf_counter() + duration
        while time.perf_counter() < end_time:
            pass
    
    def _enter_repl(self):
        # Interrupt anything currently running
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.3)
        self.ser.reset_input_buffer()
        # Enter raw REPL briefly to force a known state
        self.ser.write(b"\x01")
        self._wait_ready(0.3)
        self.ser.reset_input_buffer()
        # Immediately exit back to normal REPL — this is the key fix.
        # Previously this stopped here, leaving the device in raw REPL.
        # Everything after __init__ (mkdir, _exec_capture) assumes normal REPL,
        # so we must land here cleanly.
        self.ser.write(b"\x02")
        self._wait_ready(0.3)
        self.ser.reset_input_buffer()
    
    def _exec(self, code: str):
        self.ser.write(code.encode() + b"\r")
        self._wait_ready(REPL_DELAY)
    
    def _exec_capture(self, code: str) -> str:
        self._exec("import sys")
        self._exec("sys.stdout.write('<<<')")
        
        for line in code.strip().splitlines():
            self._exec(line)
        
        self._exec("sys.stdout.write('>>>')")
        
        out = b""
        start = time.perf_counter()
        while time.perf_counter() - start < 2:
            if self.ser.in_waiting:
                out += self.ser.read(self.ser.in_waiting)
            if b">>>" in out:
                break
        
        data = out.decode(errors="ignore")
        if "Traceback" in data:
            raise MicroPyError(data)
        
        return data.split("<<<")[-1].split(">>>")[0]
    
    # ----------------------------------------------------------
    # Option 1: Sequential Directory Creation (Normal REPL)
    # Each mkdir is done individually with verification.
    # Raw REPL is NEVER used here — only in put().
    # ----------------------------------------------------------
    
    def mkdir(self, path):
        """Create a single directory in normal REPL and verify it exists.
        Returns True if directory exists after the call, False otherwise."""
        # Step 1: Create the directory (ignore if already exists)
        self._exec_capture(f"""
import os
try:
    os.mkdir("{path}")
except OSError:
    pass
""")
        # Step 2: Verify the directory actually exists
        result = self._exec_capture(f"""
import os
try:
    os.stat("{path}")
    print("EXISTS")
except OSError:
    print("MISSING")
""")
        return "EXISTS" in result
    
    def ensure_dirs(self, remote_path: str):
        """Create each directory in the path sequentially with verification.
        
        Flow:
            1. Split remote_path into directory parts (exclude filename)
            2. For each directory level, call mkdir() which:
               a. Creates the directory in normal REPL
               b. Verifies the directory exists
               c. Returns True/False
            3. If any directory fails verification, raise MicroPyError immediately
            4. Raw REPL is never entered here — put() handles that separately
        """
        parts = remote_path.split("/")[:-1]  # exclude the filename
        cur = ""
        for p in parts:
            cur = f"{cur}/{p}" if cur else p
            exists = self.mkdir(cur)
            if not exists:
                raise MicroPyError(f"Failed to create directory: {cur}")
    
    def put(self, local: Path, remote: str):
        """Upload a file to the device using chunked writes.
        
        Flow:
            1. Assumes directories already exist (call ensure_dirs() first)
            2. Cleanly enters raw REPL:
               a. Send Ctrl+C twice to interrupt anything running
               b. Flush input buffer
               c. Send Ctrl+A to enter raw REPL
               d. Flush the raw REPL entry prompt
            3. Build the full write script as a single block
            4. Send Ctrl+D to execute
            5. Wait for completion, check for errors
            6. Exit raw REPL with Ctrl+B back to normal REPL
        """
        CHUNK_SIZE = 128

        data = local.read_bytes()
        total_len = len(data)
        num_chunks = (total_len + CHUNK_SIZE - 1) // CHUNK_SIZE

        # --- Step 1: Cleanly enter raw REPL ---
        # Interrupt any running code first
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.3)
        # Flush any leftover data in buffer
        self.ser.reset_input_buffer()
        # Now enter raw REPL
        self.ser.write(b"\x01")
        self._wait_ready(0.5)
        # Flush the "enter raw REPL" prompt so it doesn't pollute our output
        self.ser.reset_input_buffer()

        # --- Step 2: Build the full file-write script ---
        lines = []
        lines.append('import os')
        lines.append('try:')
        lines.append(f'    os.remove("{remote}")')
        lines.append('except OSError:')
        lines.append('    pass')
        lines.append(f'f = open("{remote}", "wb")')

        for i in range(num_chunks):
            chunk = data[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE]
            lines.append(f'f.write({repr(chunk)})')

        lines.append('f.close()')
        lines.append('print("OK")')

        code = "\r\n".join(lines) + "\r\n"
        self.ser.write(code.encode())
        self._wait_ready(0.1)

        # --- Step 3: Execute with Ctrl+D ---
        self.ser.write(b"\x04")

        # --- Step 4: Wait for completion and check for errors ---
        output = b""
        start = time.perf_counter()
        while time.perf_counter() - start < 5:  # 5s timeout for large files
            if self.ser.in_waiting:
                output += self.ser.read(self.ser.in_waiting)
            # Raw REPL returns ">" after successful execution
            if b">" in output:
                break
            time.sleep(0.05)

        if b"Traceback" in output:
            # Exit raw REPL before raising so device is in a clean state
            self.ser.write(b"\x02")
            self._wait_ready(0.2)
            raise MicroPyError(output.decode(errors="ignore"))

        # --- Step 5: Exit raw REPL back to normal REPL ---
        self.ser.write(b"\x02")
        self._wait_ready(0.2)
    
    def exit_raw_repl(self):
        """Safety call — ensure we're back in normal REPL"""
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.1)
        self.ser.write(b"\x02")
        self._wait_ready(0.1)


# ============================================================
# ================= LINUX-STYLE UI COMPONENTS ================
# ============================================================

class LinuxButton:
    """Flat Linux-style button"""
    def __init__(self, x, y, width, height, text, primary=False):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.primary = primary
        self.hovered = False
        self.font = pygame.font.Font(None, 20)
    
    def draw(self, screen):
        if self.primary:
            color = Colors.ACCENT_HOVER if self.hovered else Colors.ACCENT
            text_color = Colors.TEXT
        else:
            color = Colors.HOVER if self.hovered else Colors.CARD
            text_color = Colors.TEXT
        
        pygame.draw.rect(screen, color, self.rect, border_radius=4)
        pygame.draw.rect(screen, Colors.BORDER, self.rect, 1, border_radius=4)
        
        text_surf = self.font.render(self.text, True, text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)
    
    def handle_click(self, pos):
        if self.rect.collidepoint(pos):
            return True
        return False
    
    def handle_motion(self, pos):
        self.hovered = self.rect.collidepoint(pos)


class LinuxCheckbox:
    """Linux-style checkbox"""
    def __init__(self, x, y, text, checked=False):
        self.rect = pygame.Rect(x, y, 18, 18)
        self.text = text
        self.checked = checked
        self.hovered = False
        self.font = pygame.font.Font(None, 20)
    
    def toggle(self):
        self.checked = not self.checked
    
    def handle_click(self, pos):
        if self.rect.collidepoint(pos):
            self.toggle()
            return True
        return False
    
    def handle_motion(self, pos):
        self.hovered = self.rect.collidepoint(pos)
    
    def draw(self, screen):
        pygame.draw.rect(screen, Colors.BORDER, self.rect, 1)
        if self.checked:
            pygame.draw.rect(screen, Colors.ACCENT, self.rect.inflate(-2, -2))
            check_surf = self.font.render("✓", True, Colors.TEXT)
            screen.blit(check_surf, (self.rect.x + 2, self.rect.y))
        
        text_surf = self.font.render(self.text, True, Colors.TEXT)
        screen.blit(text_surf, (self.rect.right + 8, self.rect.y + 1))


class LinuxProgressBar:
    """Linux-style progress bar"""
    def __init__(self, x, y, width, height):
        self.rect = pygame.Rect(x, y, width, height)
        self.progress = 0.0
        self.target_progress = 0.0
    
    def set_progress(self, value):
        self.target_progress = max(0.0, min(1.0, value))
    
    def update(self):
        if abs(self.progress - self.target_progress) > 0.001:
            distance = self.target_progress - self.progress
            self.progress += distance * 0.22
        else:
            self.progress = self.target_progress
    
    def draw(self, screen):
        pygame.draw.rect(screen, Colors.PROGRESS_TRACK, self.rect, border_radius=3)
        
        if self.progress > 0:
            fill_rect = self.rect.copy()
            fill_rect.width = int(self.rect.width * self.progress)
            pygame.draw.rect(screen, Colors.ACCENT, fill_rect, border_radius=3)
        
        pygame.draw.rect(screen, Colors.BORDER, self.rect, 1, border_radius=3)
        
        font = pygame.font.Font(None, 18)
        percentage = int(self.progress * 100)
        text = font.render(f"{percentage}%", True, Colors.TEXT)
        text_rect = text.get_rect(center=self.rect.center)
        screen.blit(text, text_rect)


class LogPanel:
    """Linux-style log panel"""
    def __init__(self, x, y, width, height):
        self.rect = pygame.Rect(x, y, width, height)
        self.entries = deque(maxlen=100)
        self.scroll_offset = 0
        self.target_scroll = 0
        self.font = pygame.font.Font(None, 18)
        self.time_font = pygame.font.Font(None, 16)
    
    def add_log(self, message, msg_type="info"):
        timestamp = time.strftime("%H:%M:%S")
        self.entries.append((timestamp, message, msg_type))
        
        total_height = len(self.entries) * 20
        max_scroll = max(0, total_height - self.rect.height + 10)
        self.target_scroll = max_scroll
    
    def update(self):
        if abs(self.scroll_offset - self.target_scroll) > 0.5:
            distance = self.target_scroll - self.scroll_offset
            self.scroll_offset += distance * 0.22
        else:
            self.scroll_offset = self.target_scroll
    
    def draw(self, screen):
        pygame.draw.rect(screen, Colors.CARD, self.rect)
        pygame.draw.rect(screen, Colors.BORDER, self.rect, 1)
        
        screen.set_clip(self.rect.inflate(-4, -4))
        
        y = self.rect.y + 5 - self.scroll_offset
        
        for timestamp, message, msg_type in self.entries:
            if y + 20 < self.rect.y:
                y += 20
                continue
            if y > self.rect.y + self.rect.height:
                break
            
            time_surf = self.time_font.render(f"[{timestamp}]", True, Colors.TEXT_DIM)
            screen.blit(time_surf, (self.rect.x + 8, y))
            
            if msg_type == "success":
                color = Colors.SUCCESS
            elif msg_type == "error":
                color = Colors.ERROR
            elif msg_type == "warning":
                color = Colors.WARNING
            else:
                color = Colors.TEXT
            
            msg_surf = self.font.render(message[:70], True, color)
            screen.blit(msg_surf, (self.rect.x + 90, y))
            
            y += 20
        
        screen.set_clip(None)
        
        total_height = len(self.entries) * 20
        if total_height > self.rect.height:
            scrollbar_height = max(20, int(self.rect.height * self.rect.height / total_height))
            max_scroll = total_height - self.rect.height + 10
            scroll_ratio = self.scroll_offset / max_scroll if max_scroll > 0 else 0
            scrollbar_y = self.rect.y + int(scroll_ratio * (self.rect.height - scrollbar_height))
            
            thumb_rect = pygame.Rect(self.rect.right - 6, scrollbar_y, 4, scrollbar_height)
            pygame.draw.rect(screen, Colors.ACCENT, thumb_rect, border_radius=2)
    
    def handle_scroll(self, delta):
        total_height = len(self.entries) * 20
        max_scroll = max(0, total_height - self.rect.height + 10)
        self.target_scroll = max(0, min(self.target_scroll + delta, max_scroll))


# ============================================================
# ===================== MAIN APPLICATION =====================
# ============================================================

class CalSciApp:
    """Linux-style main application"""
    def __init__(self):
        pygame.init()
        
        self.width = 800
        self.height = 600
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("CalSci Flasher")
        
        self.title_font = pygame.font.Font(None, 32)
        self.font = pygame.font.Font(None, 20)
        
        self.header_height = 60
        
        button_width = 200
        button_height = 40
        button_spacing = 15
        start_y = self.header_height + 30
        center_x = self.width // 2 - button_width // 2
        
        self.update_btn = LinuxButton(
            center_x, start_y, button_width, button_height, "Download Updates"
        )
        
        self.flash_btn = LinuxButton(
            center_x, start_y + button_height + button_spacing, 
            button_width, button_height, "Flash All Files", primary=True
        )
        
        self.upload_btn = LinuxButton(
            center_x, start_y + (button_height + button_spacing) * 2,
            button_width, button_height, "Upload Selected..."
        )
        
        progress_y = start_y + (button_height + button_spacing) * 3 + 20
        self.progress_bar = LinuxProgressBar(50, progress_y, self.width - 100, 25)
        
        self.auto_retry_checkbox = LinuxCheckbox(50, progress_y + 35, "Auto-retry on failure (hard reset + 5s wait)", checked=True)
        
        log_y = progress_y + 70
        self.log_panel = LogPanel(20, log_y, self.width - 40, self.height - log_y - 20)
        
        self.running = True
        self.clock = pygame.time.Clock()
        self.operation_in_progress = False
        self.selection_dialog = None
        self.log_queue = Queue()
    
    def log(self, message, msg_type="info"):
        self.log_queue.put((message, msg_type))
    
    def process_log_queue(self):
        while True:
            try:
                message, msg_type = self.log_queue.get_nowait()
                self.log_panel.add_log(message, msg_type)
            except Empty:
                break
    
    def draw(self):
        self.screen.fill(Colors.BG)
        
        header_rect = pygame.Rect(0, 0, self.width, self.header_height)
        pygame.draw.rect(self.screen, Colors.HEADER, header_rect)
        pygame.draw.line(self.screen, Colors.BORDER, (0, self.header_height), 
                        (self.width, self.header_height))
        
        title_surf = self.title_font.render("CalSci Flasher", True, Colors.TEXT)
        title_rect = title_surf.get_rect(midleft=(20, self.header_height // 2))
        self.screen.blit(title_surf, title_rect)
        
        subtitle = self.font.render("ESP32 MicroPython Tool", True, Colors.TEXT_DIM)
        self.screen.blit(subtitle, (20, self.header_height // 2 + 15))
        
        self.update_btn.draw(self.screen)
        self.flash_btn.draw(self.screen)
        self.upload_btn.draw(self.screen)
        
        self.progress_bar.update()
        self.progress_bar.draw(self.screen)
        
        self.auto_retry_checkbox.draw(self.screen)
        
        self.log_panel.update()
        self.log_panel.draw(self.screen)
        
        if self.selection_dialog:
            self.selection_dialog.update()
            self.selection_dialog.draw()
        
        pygame.display.flip()
    
    def handle_update(self):
        self.operation_in_progress = True
        self.progress_bar.set_progress(0.0)
        
        try:
            self.log("Checking repository...", "info")
            self.progress_bar.set_progress(0.1)
            ensure_repo(lambda m, t="info": self.log(m, t))
            
            self.log("Fetching updates...", "info")
            self.progress_bar.set_progress(0.3)
            ahead, behind = repo_status(lambda m, t="info": self.log(m, t))
            
            if behind > 0:
                self.log(f"Downloading {behind} commits...", "info")
                self.progress_bar.set_progress(0.6)
                pull_repo(lambda m, t="info": self.log(m, t))
                self.log("Update complete", "success")
            else:
                self.log("Already up to date", "success")
            
            self.progress_bar.set_progress(1.0)
        
        except Exception as e:
            self.log(f"Error: {e}", "error")
            self.progress_bar.set_progress(0.0)
        
        finally:
            self.operation_in_progress = False
    
    # ----------------------------------------------------------
    # Helper: performs the upload of a single file with the
    # Option 1 flow: ensure_dirs (normal REPL) → put (raw REPL)
    # Handles auto-retry with hard reset if enabled.
    # ----------------------------------------------------------
    def _upload_single_file(self, flasher, port, path, remote_path, auto_retry):
        """Upload one file using Option 1 flow.
        
        Returns:
            (flasher, True)  — success, possibly a new flasher instance after retry
            (flasher, False) — failed after all retries
        """
        for attempt in range(2):  # attempt 0 = initial, attempt 1 = retry
            try:
                # Step 1: Create directories sequentially in normal REPL (verified)
                flasher.ensure_dirs(remote_path)
                # Step 2: Upload the file in raw REPL (enters and exits cleanly)
                flasher.put(path, remote_path)
                return flasher, True  # Success
            except Exception as e:
                if attempt == 0 and auto_retry:
                    # Hard reset the device and reconnect
                    self.log(f"Upload failed: {path.name}, retrying after hard reset...", "warning")
                    try:
                        flasher.ser.dtr = False
                        flasher.ser.rts = True
                        time.sleep(0.1)
                        flasher.ser.dtr = True
                        flasher.ser.rts = False
                        time.sleep(0.1)
                        flasher.ser.close()
                    except:
                        pass
                    time.sleep(5)  # Wait for device to reboot
                    flasher = MicroPyFlasher(port)  # Reconnect
                    # Loop continues to attempt 1
                else:
                    # No retry left or retry disabled
                    return flasher, False
        return flasher, False
    
    def handle_flash(self):
        self.operation_in_progress = True
        self.progress_bar.set_progress(0.0)
        auto_retry = self.auto_retry_checkbox.checked
        
        try:
            ports = find_esp32_ports()
            if not ports:
                raise RuntimeError("No ESP32 detected")
            
            port = ports[0]
            self.log(f"ESP32 found: {port}", "success")
            
            self.progress_bar.set_progress(0.05)
            flasher = MicroPyFlasher(port)
            
            files = [p for p in ROOT.rglob("*") if p.is_file() and not should_skip(p)]
            total_size = sum(p.stat().st_size for p in files)
            
            self.log(f"Uploading {len(files)} files...", "info")
            
            uploaded = 0
            failed_files = []
            
            for i, path in enumerate(files, 1):
                remote_path = path.relative_to(ROOT).as_posix()
                
                flasher, success = self._upload_single_file(
                    flasher, port, path, remote_path, auto_retry
                )
                
                if success:
                    uploaded += path.stat().st_size
                    progress = 0.05 + (uploaded / total_size) * 0.95
                    self.progress_bar.set_progress(progress)
                    self.log(f"[{i}/{len(files)}] {path.name}", "info")
                else:
                    failed_files.append(path.name)
                    self.log(f"Skipping failed file: {path.name}", "warning")
            
            flasher.exit_raw_repl()
            flasher.close()
            
            if failed_files:
                self.log(f"Flash complete with {len(failed_files)} failures: {', '.join(failed_files)}", "warning")
            else:
                self.log("Flash complete!", "success")
                self.progress_bar.set_progress(1.0)
        
        except Exception as e:
            self.log(f"Error: {str(e)[:50]}", "error")
            self.progress_bar.set_progress(0.0)
        
        finally:
            self.operation_in_progress = False
    
    def handle_upload_selected(self):
        self.log("Scanning files...", "info")
        
        files = [p for p in ROOT.rglob("*") if p.is_file() and not should_skip(p)]
        
        if not files:
            self.log("No files found", "error")
            return
        
        self.log(f"Found {len(files)} files", "info")
        
        pre_selected = SelectionMemory.load_selections()
        if pre_selected:
            self.log(f"Loaded {len(pre_selected)} previous selections", "info")
        
        self.selection_dialog = FileSelectionDialog(self.screen, files, ROOT, pre_selected)
        
        clock = pygame.time.Clock()
        
        while self.selection_dialog.result is None:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.selection_dialog.result = "cancel"
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.selection_dialog.result = "cancel"
                self.selection_dialog.handle_event(event)
            
            if self.selection_dialog.result is not None:
                break
            
            self.draw()
            clock.tick(60)
        
        result = self.selection_dialog.result
        selected_files = self.selection_dialog.get_selected_files()
        
        self.selection_dialog = None
        
        if result == "cancel" or not selected_files:
            if result == "cancel":
                self.log("Upload cancelled", "info")
            else:
                self.log("No files selected", "info")
            return
        
        self.log(f"Selected {len(selected_files)} files for upload", "info")
        
        SelectionMemory.save_selections(selected_files)
        self.log(f"Saved {len(selected_files)} selections", "info")
        
        def upload():
            self.operation_in_progress = True
            self.progress_bar.set_progress(0.0)
            auto_retry = self.auto_retry_checkbox.checked
            
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No ESP32 detected")
                
                port = ports[0]
                self.log(f"ESP32 found: {port}", "success")
                
                flasher = MicroPyFlasher(port)
                total_size = sum(p.stat().st_size for p in selected_files)
                
                self.log(f"Uploading {len(selected_files)} files...", "info")
                self.progress_bar.set_progress(0.1)
                
                uploaded = 0
                failed_files = []
                
                for i, path in enumerate(selected_files, 1):
                    remote_path = path.relative_to(ROOT).as_posix()
                    
                    flasher, success = self._upload_single_file(
                        flasher, port, path, remote_path, auto_retry
                    )
                    
                    if success:
                        uploaded += path.stat().st_size
                        progress = 0.1 + (uploaded / total_size) * 0.9
                        self.progress_bar.set_progress(progress)
                        self.log(f"[{i}/{len(selected_files)}] {path.name}", "info")
                    else:
                        failed_files.append(path.name)
                        self.log(f"Skipping failed file: {path.name}", "warning")
                
                flasher.exit_raw_repl()
                flasher.close()
                
                if failed_files:
                    self.log(f"Upload complete with {len(failed_files)} failures: {', '.join(failed_files)}", "warning")
                else:
                    self.log("Upload complete!", "success")
                    self.progress_bar.set_progress(1.0)
                
                self.log("Selections saved for next upload", "info")
            
            except Exception as e:
                self.log(f"Error: {str(e)[:50]}", "error")
                self.progress_bar.set_progress(0.0)
            
            finally:
                self.operation_in_progress = False
        
        threading.Thread(target=upload, daemon=True).start()
    
    def run(self):
        while self.running:
            self.process_log_queue()
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.selection_dialog:
                            self.selection_dialog.result = "cancel"
                        else:
                            self.running = False
                
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 4:
                        if not self.selection_dialog:
                            self.log_panel.handle_scroll(-40)
                    elif event.button == 5:
                        if not self.selection_dialog:
                            self.log_panel.handle_scroll(40)
                
                elif event.type == pygame.MOUSEMOTION:
                    if not self.selection_dialog:
                        self.update_btn.handle_motion(event.pos)
                        self.flash_btn.handle_motion(event.pos)
                        self.upload_btn.handle_motion(event.pos)
                        self.auto_retry_checkbox.handle_motion(event.pos)
                
                if not self.selection_dialog and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if not self.operation_in_progress:
                        if self.auto_retry_checkbox.handle_click(event.pos):
                            pass
                        elif self.update_btn.handle_click(event.pos):
                            threading.Thread(target=self.handle_update, daemon=True).start()
                        elif self.flash_btn.handle_click(event.pos):
                            threading.Thread(target=self.handle_flash, daemon=True).start()
                        elif self.upload_btn.handle_click(event.pos):
                            self.handle_upload_selected()
            
            self.draw()
            self.clock.tick(60)
        
        pygame.quit()
=======
import shutil
import subprocess
import threading
import hashlib
from pathlib import Path
from queue import Queue, Empty
import time
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QProgressBar, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QSplitter,
    QFrame, QStatusBar, QMessageBox, QPlainTextEdit, QTabWidget, QMenu,
    QDialog
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QColor, QFont, QAction, QTextCursor

# Import from modular files
from config import ROOT, FIRMWARE_BIN
from utils import find_esp32_ports, ensure_repo, delete_repo, repo_status, pull_repo, get_all_files
from flasher import MicroPyFlasher, MicroPyError, flash_firmware, confirm_bootloader, wait_for_reset_signal
from signal_bridge import SignalBridge
from dialogs import ESP32FileSelectionDialog
from filebrowser import ESP32FileBrowser



# ============================================================
# ================= MAIN APPLICATION ==========================
# ============================================================

class CalSciApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CalSci Flasher")
        self.setMinimumSize(820, 660)

        self.bridge = SignalBridge()
        self.bridge.log_signal.connect(self._on_log)
        self.bridge.progress_signal.connect(self._on_progress)
        self.bridge.operation_done_signal.connect(self._on_operation_done)
        self.bridge.device_status_signal.connect(self._update_device_status)

        self.operation_in_progress = False
        self.file_browser = None
        self._device_connected = False
        self.simulator_process = None
        
        self._build_ui()
        self._apply_stylesheet()

        self.device_timer = QTimer()
        self.device_timer.timeout.connect(self._check_device_status)
        self.device_timer.start(2000)
        self._check_device_status()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 14, 20, 14)

        title_label = QLabel("CalSci Flasher")
        title_label.setObjectName("titleLabel")
        header_layout.addWidget(title_label)

        subtitle_label = QLabel("CalSci MicroPython Uploader")
        subtitle_label.setObjectName("subtitleLabel")
        header_layout.addWidget(subtitle_label)

        header_layout.addStretch()

        self.esp_status_label = QLabel("● No device")
        self.esp_status_label.setObjectName("espStatusDisconnected")
        header_layout.addWidget(self.esp_status_label)

        main_layout.addWidget(header)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(16)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.update_btn = QPushButton("Download Updates")
        self.update_btn.setObjectName("btnSecondary")
        self.update_btn.clicked.connect(self._handle_update)
        left_layout.addWidget(self.update_btn)

        self.flash_btn = QPushButton("Flash All Files")
        self.flash_btn.setObjectName("btnPrimary")
        self.flash_btn.clicked.connect(self._handle_flash)
        left_layout.addWidget(self.flash_btn)

        self.flash_fw_cb = QCheckBox("Reflash firmware before upload")
        self.flash_fw_cb.setChecked(False)
        self.flash_fw_cb.setObjectName("retryCheckbox")
        left_layout.addWidget(self.flash_fw_cb)

        self.delta_btn = QPushButton("Sync (Delta)")
        self.delta_btn.setObjectName("btnSecondary")
        self.delta_btn.clicked.connect(self._handle_delta_sync)
        left_layout.addWidget(self.delta_btn)

        self.browse_btn = QPushButton("Browse CalSci Files…")
        self.browse_btn.setObjectName("btnSecondary")
        self.browse_btn.clicked.connect(self._open_file_browser)
        left_layout.addWidget(self.browse_btn)

        self.clear_btn = QPushButton("Clear All Files")
        self.clear_btn.setObjectName("btnDanger")
        self.clear_btn.clicked.connect(self._handle_clear_all)
        left_layout.addWidget(self.clear_btn)

        self.simulator_btn = QPushButton("Launch Simulator")
        self.simulator_btn.setObjectName("btnSecondary")
        self.simulator_btn.clicked.connect(self._handle_launch_simulator)
        left_layout.addWidget(self.simulator_btn)

        self.auto_retry_cb = QCheckBox("Auto-retry on failure)")
        self.auto_retry_cb.setChecked(True)
        self.auto_retry_cb.setObjectName("retryCheckbox")
        left_layout.addWidget(self.auto_retry_cb)

        left_layout.addStretch()

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(8)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setObjectName("progressBar")
        right_layout.addWidget(self.progress_bar)

        self.current_file_label = QLabel("Idle")
        self.current_file_label.setObjectName("currentFileLabel")
        right_layout.addWidget(self.current_file_label)

        self.log_panel = QTextEdit()
        self.log_panel.setReadOnly(True)
        self.log_panel.setObjectName("logPanel")
        right_layout.addWidget(self.log_panel)

        body_layout.addWidget(left_panel, stretch=1)
        body_layout.addWidget(right_panel, stretch=3)
        main_layout.addWidget(body)

        status_bar = QStatusBar()
        status_bar.showMessage("Ready")
        self.setStatusBar(status_bar)

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }

            QFrame#header {
                background-color: #141414;
                border-bottom: 1px solid #333;
            }
            QLabel#titleLabel {
                font-size: 18px;
                font-weight: 700;
                color: #f0f0f0;
                margin-right: 14px;
            }
            QLabel#subtitleLabel {
                font-size: 12px;
                color: #666;
            }
            QLabel#espStatusDisconnected {
                color: #e74c3c;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#espStatusConnected {
                color: #77b255;
                font-size: 12px;
                font-weight: 600;
            }

            QPushButton#btnPrimary {
                background-color: rgba(233, 84, 32, 0.5);
                color: #fff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 6px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: 600;
                min-width: 200px;
            }
            QPushButton#btnPrimary:hover { background-color: rgba(233, 84, 32, 0.7); }
            QPushButton#btnPrimary:pressed { background-color: rgba(233, 84, 32, 0.9); }
            QPushButton#btnPrimary:disabled { background-color: rgba(85, 85, 85, 0.5); color: #777777; border-color: rgba(85, 85, 85, 0.8); }

            QPushButton#btnSecondary {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 6px;
                padding: 12px 20px;
                font-size: 14px;
                min-width: 200px;
            }
            QPushButton#btnSecondary:hover { background-color: rgba(233, 84, 32, 0.7); }
            QPushButton#btnSecondary:pressed { background-color: rgba(233, 84, 32, 0.9); }
            QPushButton#btnSecondary:disabled { background-color: rgba(85, 85, 85, 0.5); color: #777777; border-color: rgba(85, 85, 85, 0.8); }

            QPushButton#btnDanger {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 6px;
                padding: 12px 20px;
                font-size: 14px;
                min-width: 200px;
            }
            QPushButton#btnDanger:hover { background-color: rgba(233, 84, 32, 0.7); }
            QPushButton#btnDanger:pressed { background-color: rgba(233, 84, 32, 0.9); }
            QPushButton#btnDanger:disabled { background-color: rgba(85, 85, 85, 0.5); color: #777777; border-color: rgba(85, 85, 85, 0.8); }

            QCheckBox#retryCheckbox {
                color: #a0a0a0;
                font-size: 12px;
                spacing: 8px;
                margin-top: 10px;
            }
            QCheckBox#retryCheckbox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #555;
                border-radius: 4px;
                background: #2a2a2a;
            }
            QCheckBox#retryCheckbox::indicator:hover {
                border-color: #777;
                background: #333;
            }
            QCheckBox#retryCheckbox::indicator:checked {
                background-color: #e95420;
                border-color: #e95420;
            }

            QCheckBox#preventSleepCheckbox {
                color: #a0a0a0;
                font-size: 12px;
                spacing: 8px;
                margin-top: 6px;
            }
            QCheckBox#preventSleepCheckbox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #555;
                border-radius: 4px;
                background: #2a2a2a;
            }
            QCheckBox#preventSleepCheckbox::indicator:hover {
                border-color: #777;
                background: #333;
            }
            QCheckBox#preventSleepCheckbox::indicator:checked {
                background-color: #e95420;
                border-color: #e95420;
            }

            QProgressBar#progressBar {
                height: 18px;bbbbbbbbbbbb
                border-radius: 4px;
                border: 1px solid #3a3a3a;
                background-color: #2a2a2a;
                text-align: center;
                color: #fff;
                font-size: 11px;
            }
            QProgressBar#progressBar::chunk {
                background-color: #e95420;
                border-radius: 3px;
            }

            QLabel#currentFileLabel {
                color: #777;
                font-size: 12px;
                font-style: italic;
            }

            QTextEdit#logPanel {
                background-color: #161616;
                border: 1px solid #2e2e2e;
                border-radius: 6px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                color: #c0c0c0;
            }

            QStatusBar {
                background-color: #141414;
                border-top: 1px solid #333;
                color: #666;
                font-size: 11px;
                padding: 4px 12px;
            }
        """)

    def _check_device_status(self):
        if not self.operation_in_progress:
            ports = find_esp32_ports()
            was_connected = self._device_connected
            is_connected = len(ports) > 0
            self._device_connected = is_connected

            self.bridge.device_status_signal.emit(is_connected)

    def _update_device_status(self, connected):
        if connected:
            self.esp_status_label.setText("● Device connected")
            self.esp_status_label.setObjectName("espStatusConnected")
        else:
            self.esp_status_label.setText("● No device")
            self.esp_status_label.setObjectName("espStatusDisconnected")
        self.esp_status_label.style().unpolish(self.esp_status_label)
        self.esp_status_label.style().polish(self.esp_status_label)

    def _on_log(self, message, msg_type):
        color_map = {
            "info":    "#c0c0c0",
            "success": "#77b255",
            "error":   "#eb4d4b",
            "warning": "#f2a93b",
        }
        color = color_map.get(msg_type, "#c0c0c0")
        timestamp = time.strftime("%H:%M:%S")
        html = (
            f'<span style="color:#555;">[{timestamp}]</span> '
            f'<span style="color:{color};">{message}</span><br>'
        )

        # Save current selection if any
        cursor = self.log_panel.textCursor()
        had_selection = cursor.hasSelection()
        if had_selection:
            selection_start = cursor.selectionStart()
            selection_end = cursor.selectionEnd()

        # Always insert at the end
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_panel.setTextCursor(cursor)
        self.log_panel.insertHtml(html)

        # Restore selection or auto-scroll
        if had_selection:
            # Restore the previous selection
            cursor.setPosition(selection_start)
            cursor.setPosition(selection_end, QTextCursor.MoveMode.KeepAnchor)
            self.log_panel.setTextCursor(cursor)
        else:
            # Auto-scroll to end
            self.log_panel.moveCursor(QTextCursor.MoveOperation.End)

        self.current_file_label.setText(message)

    def _on_progress(self, value):
        self.progress_bar.setValue(int(value * 100))

    def _on_operation_done(self):
        self.operation_in_progress = False
        self.update_btn.setEnabled(True)
        self.flash_btn.setEnabled(True)
        self.delta_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.simulator_btn.setEnabled(True)
        self._check_device_status()

    def _ensure_window_sequence(self, action_label):
        if self.file_browser and self.file_browser.isVisible():
            self.file_browser.close()
            if self.file_browser.isVisible():
                self.file_browser.raise_()
                self.file_browser.activateWindow()
                self._log(f"Close the File Browser before {action_label}.", "warning")
                return False
            self.file_browser = None
        return True

    def _on_file_browser_closed(self, _obj=None):
        self.file_browser = None

    def _lock_buttons(self):
        self.operation_in_progress = True
        self.update_btn.setEnabled(False)
        self.flash_btn.setEnabled(False)
        self.delta_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.simulator_btn.setEnabled(False)
        self.progress_bar.setValue(0)

    def _log(self, message, msg_type="info"):
        self.bridge.log_signal.emit(message, msg_type)

    def _open_file_browser(self):
        ports = find_esp32_ports()
        if not ports:
            QMessageBox.warning(
                self,
                "No Device",
                "No CalSci device detected.\n\nPlease connect your CalSci and try again."
            )
            return
        
        port = ports[0]
        
        if self.file_browser is None or not self.file_browser.isVisible():
            self.file_browser = ESP32FileBrowser(port, self.bridge, parent=self)
            self.file_browser.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            self.file_browser.destroyed.connect(self._on_file_browser_closed)
            self.file_browser.show()
        else:
            self.file_browser.raise_()
            self.file_browser.activateWindow()

    def _handle_update(self):
        self._lock_buttons()

        def run():
            try:
                # First, delete the existing repository
                self._log("Deleting existing repository…", "info")
                self.bridge.progress_signal.emit(0.1)
                delete_repo(self._log)

                # Then clone fresh from remote
                self._log("Cloning repository fresh…", "info")
                self.bridge.progress_signal.emit(0.4)
                ensure_repo(self._log)

                self._log("Repository updated successfully ✓", "success")
                self.bridge.progress_signal.emit(1.0)
            except Exception as e:
                self._log(f"Error: {e}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    def _handle_delta_sync(self):
        if not ROOT.exists():
            self._log("Repository not found. Click 'Download Updates' first.", "error")
            return

        local_files = get_all_files(ROOT)
        if not local_files:
            self._log("No local files found in repository", "error")
            return

        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No ESP32 device detected")

                port = ports[0]
                self._log(f"CalSci found: {port}", "success")
                self.bridge.progress_signal.emit(0.05)

                flasher = MicroPyFlasher(port)
                # self._log("soft resetting device…", "info")
                # flasher.reset_soft_automated(auto_cd="/apps/installed_apps", log_func=self._log)

                self._log("Scanning CalSci file system…", "info")
                esp32_sizes = flasher.get_file_sizes()
                self._log(f"CalSci has {len(esp32_sizes)} file(s)", "info")
                self.bridge.progress_signal.emit(0.10)

                local_map = {}
                for p in local_files:
                    remote = "/" + p.relative_to(ROOT).as_posix()
                    local_map[remote] = p

                to_upload   = []
                to_delete   = []
                unchanged   = []

                for remote, local_path in local_map.items():
                    local_size = local_path.stat().st_size
                    if remote in esp32_sizes:
                        if esp32_sizes[remote] == local_size:
                            unchanged.append(remote)
                        else:
                            to_upload.append((remote, local_path))
                    else:
                        to_upload.append((remote, local_path))

                for remote in esp32_sizes:
                    if remote not in local_map:
                        to_delete.append(remote)

                self._log("─── Sync comparison ───", "info")
                self._log(f"  Unchanged : {len(unchanged)} file(s)", "info")
                self._log(f"  To upload : {len(to_upload)} file(s)", "info")
                self._log(f"  To delete : {len(to_delete)} file(s)", "info")
                self.bridge.progress_signal.emit(0.15)

                if unchanged:
                    self._log("  ─ Unchanged (skipped):", "info")
                    for r in sorted(unchanged):
                        self._log(f"      ✓ {r}", "info")

                if to_upload:
                    self._log("  ─ To upload:", "info")
                    for remote, local_path in sorted(to_upload, key=lambda x: x[0]):
                        local_size = local_path.stat().st_size
                        if remote in esp32_sizes:
                            self._log(f"      ↻ {remote}  ({esp32_sizes[remote]} → {local_size} bytes, changed)", "warning")
                        else:
                            self._log(f"      + {remote}  ({local_size} bytes, new)", "warning")

                if to_delete:
                    self._log("  ─ To delete (not in local repo):", "info")
                    for r in sorted(to_delete):
                        self._log(f"      - {r}  ({esp32_sizes[r]} bytes)", "warning")

                self._log("───────────────────────", "info")

                if not to_upload and not to_delete:
                    self._log("Everything is in sync ✓", "success")
                    self.bridge.progress_signal.emit(1.0)
                    flasher.close()
                    return

                if to_delete:
                    self._log(f"Deleting {len(to_delete)} stale file(s)…", "warning")
                    for i, remote in enumerate(sorted(to_delete), 1):
                        if flasher.delete_file(remote):
                            self._log(f"  [{i}/{len(to_delete)}] Deleted: {remote}", "info")
                        else:
                            self._log(f"  [{i}/{len(to_delete)}] Failed: {remote}", "warning")
                    self.bridge.progress_signal.emit(0.30)

                if to_upload:
                    files_for_sync = [lp for _, lp in to_upload]
                    flasher.sync_folder_structure(files_for_sync, self._log)
                    self.bridge.progress_signal.emit(0.35)

                    total_size = max(sum(lp.stat().st_size for _, lp in to_upload), 1)
                    uploaded_size = 0
                    failed = []
                    auto_retry = self.auto_retry_cb.isChecked()

                    self._log(f"Uploading {len(to_upload)} file(s)…", "info")

                    for i, (remote, local_path) in enumerate(sorted(to_upload, key=lambda x: x[0]), 1):
                        remote_rel = remote.lstrip("/")

                        flasher, success = self._upload_single_file(
                            flasher, port, local_path, remote_rel, auto_retry,
                            ensure_dirs=False, use_raw=True
                        )

                        if success:
                            uploaded_size += max(local_path.stat().st_size, 1)
                            progress = 0.35 + (uploaded_size / total_size) * 0.65
                            self.bridge.progress_signal.emit(progress)
                            self._log(f"  [{i}/{len(to_upload)}] ⬆  {remote}  ({local_path.stat().st_size} bytes)", "info")
                        else:
                            failed.append(remote)
                            self._log(f"  [{i}/{len(to_upload)}] Failed: {remote}", "warning")

                    if failed:
                        self._log(f"Sync done with {len(failed)} upload failure(s)", "warning")
                    else:
                        self._log("Sync complete ✓", "success")
                        self.bridge.progress_signal.emit(1.0)
                else:
                    self._log("Sync complete ✓", "success")
                    self.bridge.progress_signal.emit(1.0)

                flasher.exit_raw_repl()
                flasher.close()

            except Exception as e:
                self._log(f"Error: {str(e)[:80]}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    def _handle_flash(self):
        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No CalSci device detected")

                port = ports[0]
                self._log(f"CalSci found: {port}", "success")
                self.bridge.progress_signal.emit(0.05)

                if self.flash_fw_cb.isChecked():
                    self._log("Press and hold BOOT, then tap RESET to enter bootloader mode.", "warning")
                    port = confirm_bootloader(port, log_func=self._log)
                    self._log("Starting erase + flash in 3 seconds…", "info")
                    for remaining in range(3, 0, -1):
                        self._log(f"  Starting erase/flash in {remaining}s", "info")
                        time.sleep(1)
                    self._log(f"Erasing + flashing firmware: {FIRMWARE_BIN.name}", "info")
                    port = flash_firmware(port, FIRMWARE_BIN, log_func=self._log, enter_bootloader=False)
                    self._log("Reset CalSci now.", "warning")
                    port = wait_for_reset_signal(port, log_func=self._log)
                    self._log("Starting upload in 3 seconds…", "info")
                    for remaining in range(3, 0, -1):
                        self._log(f"  Starting upload in {remaining}s", "info")
                        time.sleep(1)

                flasher = MicroPyFlasher(port)
                # self._log("Clearing all files from ESP32...", "warning")
                # flasher.clean_all(self._log)
                # self._log("All files cleared", "success")
                
                files = get_all_files(ROOT)

                if not files:
                    self._log("No files to upload", "info")
                    return

                flasher.sync_folder_structure(files, self._log)
                self.bridge.progress_signal.emit(0.05)

                total_size = max(sum(p.stat().st_size for p in files), 1)
                uploaded = 0
                failed_files = []
                auto_retry = self.auto_retry_cb.isChecked()

                self._log(f"Uploading {len(files)} files…", "info")

                for i, path in enumerate(files, 1):
                    remote_path = path.relative_to(ROOT).as_posix()

                    flasher, success = self._upload_single_file(
                        flasher, port, path, remote_path, auto_retry,
                        ensure_dirs=False, use_raw=True
                    )

                    if success:
                        uploaded += max(path.stat().st_size, 1)
                        self.bridge.progress_signal.emit(0.1 + (uploaded / total_size) * 0.9)
                        self._log(f"[{i}/{len(files)}] {path.name}", "info")
                    else:
                        failed_files.append(path.name)
                        self._log(f"⚠ Skipped: {path.name}", "warning")

                flasher.exit_raw_repl()
                flasher.close()

                if failed_files:
                    self._log(f"Done with {len(failed_files)} failure(s)", "warning")
                else:
                    self._log("Flash complete ✓", "success")
                    self.bridge.progress_signal.emit(1.0)

            except Exception as e:
                self._log(f"Error: {str(e)[:80]}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    def _handle_clear_all(self):
        if not self._ensure_window_sequence("clearing all files"):
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Clear All",
            "Are you sure you want to DELETE ALL FILES from CalSci?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )

        if confirm != QMessageBox.StandardButton.Yes:
            self._log("Clear cancelled", "info")
            return

        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No CalSci device detected")

                port = ports[0]
                self._log(f"CalSci found: {port}", "success")

                flasher = MicroPyFlasher(port)
                self._log("Clearing all files from CalSci...", "warning")
                flasher.clean_all(self._log)
                flasher.close()

                self._log("All files cleared ✓", "success")
                self.bridge.progress_signal.emit(1.0)

            except Exception as e:
                self._log(f"Error: {str(e)[:80]}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()
        
        threading.Thread(target=run, daemon=True).start()

    def _handle_launch_simulator(self):
        if not self._ensure_window_sequence("launching the simulator"):
            return

        if self.simulator_process and self.simulator_process.poll() is None:
            self._log("Simulator already running. Close it before launching another.", "warning")
            if self.statusBar():
                self.statusBar().showMessage("Simulator already running. Close it before launching another.")
            return

        try:
            # Launch the simulator in a separate process
            simulator_dir = Path(__file__).parent / "calsci_simulator"
            simulator_path = simulator_dir / "main.py"
            if not simulator_path.exists():
                raise FileNotFoundError(f"Simulator entry not found: {simulator_path}")

            python_exe = sys.executable
            if getattr(sys, "frozen", False):
                python_exe = shutil.which("python") or shutil.which("python3")
                if not python_exe:
                    raise RuntimeError("Python interpreter not found to launch simulator")

            self.simulator_process = subprocess.Popen(
                [python_exe, str(simulator_path)],
                cwd=str(simulator_dir)
            )
            self._log("Simulator launched ✓", "success")
        except Exception as e:
            self.simulator_process = None
            self._log(f"Failed to launch simulator: {e}", "error")

    def _handle_delete_selected(self):
        if not self._ensure_window_sequence("opening the delete dialog"):
            return

        self._lock_buttons()

        def run():
            try:
                ports = find_esp32_ports()
                if not ports:
                    raise RuntimeError("No CalSci device detected")

                port = ports[0]
                self._log(f"CalSci found: {port}", "success")

                flasher = MicroPyFlasher(port)

                self._log("Reading CalSci file system...", "info")
                esp_files, esp_dirs = flasher.list_esp32_files()
                flasher.close()

                if not esp_files and not esp_dirs:
                    self._log("CalSci is empty — nothing to delete", "info")
                    self.bridge.operation_done_signal.emit()
                    return

                self._log(f"Found {len(esp_files)} file(s), {len(esp_dirs)} folder(s)", "info")

                self.bridge.show_delete_dialog_signal.emit(esp_files, esp_dirs, port)

            except Exception as e:
                self._log(f"Error: {str(e)[:80]}", "error")
                self.bridge.progress_signal.emit(0.0)
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    def _show_delete_dialog(self, esp_files, esp_dirs, port):
        if not self._ensure_window_sequence("opening the delete dialog"):
            self.bridge.operation_done_signal.emit()
            return

        dialog = ESP32FileSelectionDialog(esp_files, esp_dirs, parent=self)
        result = dialog.exec()

        if result != QDialog.DialogCode.Accepted:
            self._log("Delete cancelled", "info")
            self.bridge.operation_done_signal.emit()
            return

        selected_items = dialog.get_selected_items()
        if not selected_items:
            self._log("No items selected", "info")
            self.bridge.operation_done_signal.emit()
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to DELETE {len(selected_items)} item(s)?\n\nThis cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )

        if confirm != QMessageBox.StandardButton.Yes:
            self._log("Delete cancelled", "info")
            self.bridge.operation_done_signal.emit()
            return

        self._log(f"Deleting {len(selected_items)} item(s)...", "warning")
        self._perform_deletion(selected_items, port)

    def _perform_deletion(self, selected_items, port):
        def run():
            try:
                flasher = MicroPyFlasher(port)

                total = len(selected_items)
                deleted = 0
                failed = 0

                files_to_delete = [(p, t) for p, t in selected_items if t == "file"]
                dirs_to_delete  = [(p, t) for p, t in selected_items if t == "folder"]

                for path, _ in files_to_delete:
                    if flasher.delete_file(path):
                        self._log(f"  Deleted: {path}", "info")
                        deleted += 1
                    else:
                        self._log(f"  Failed: {path}", "warning")
                        failed += 1
                    self.bridge.progress_signal.emit(deleted / max(total, 1))

                dirs_to_delete.sort(key=lambda x: x[0].count("/"), reverse=True)
                for path, _ in dirs_to_delete:
                    if flasher.remove_dir(path):
                        self._log(f"  📁  Deleted folder: {path}", "info")
                        deleted += 1
                    else:
                        self._log(f"  Failed folder: {path}", "warning")
                        failed += 1
                    self.bridge.progress_signal.emit(deleted / max(total, 1))

                flasher.close()

                if failed > 0:
                    self._log(f"Deletion done with {failed} failure(s)", "warning")
                else:
                    self._log(f"Successfully deleted {deleted} item(s) ✓", "success")
                    self.bridge.progress_signal.emit(1.0)

            except Exception as e:
                self._log(f"Error during deletion: {str(e)[:80]}", "error")
                self.bridge.progress_signal.emit(0.0)
            finally:
                self.bridge.operation_done_signal.emit()

        threading.Thread(target=run, daemon=True).start()

    def _upload_single_file(self, flasher, port, path, remote_path, auto_retry, ensure_dirs=True, use_raw=False):
        for attempt in range(2):
            try:
                if ensure_dirs:
                    flasher.ensure_dirs(remote_path)
                if use_raw:
                    if not flasher.is_raw_repl():
                        flasher.enter_raw_repl()
                    flasher.put_raw(path, remote_path)
                else:
                    flasher.put(path, remote_path)
                return flasher, True
            except Exception as e:
                if attempt == 0 and auto_retry:
                    self._log(f"Retry → {path.name} ( )", "warning")
                    try:
                        flasher.ser.dtr = False
                        flasher.ser.rts = True
                        # time.sleep(0.1)
                        flasher.ser.dtr = True
                        flasher.ser.rts = False
                        # time.sleep(0.1)
                        flasher.ser.close()
                    except Exception:
                        pass
                    time.sleep(3)
                    flasher = MicroPyFlasher(port)
                    if use_raw:
                        flasher.enter_raw_repl()
                else:
                    self._log(f"Failed: {path.name} — {str(e)[:50]}", "error")
                    return flasher, False
        return flasher, False

    def closeEvent(self, event):
        if self.simulator_process and self.simulator_process.poll() is None:
            self._log("Simulator running. Close it before exiting.", "warning")
            if self.statusBar():
                self.statusBar().showMessage("Simulator running. Close it before exiting.")
            event.ignore()
            return

        event.accept()
>>>>>>> bb7d8446cf7c856463161957c17a2351ef80c17f


# ============================================================
# ===================== ENTRY POINT ==========================
# ============================================================

def main():
<<<<<<< HEAD
    app = CalSciApp()
    app.run()
=======
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = CalSciApp()
    window.show()
    sys.exit(app.exec())

>>>>>>> bb7d8446cf7c856463161957c17a2351ef80c17f

if __name__ == "__main__":
    main()