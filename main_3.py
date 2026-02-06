import sys
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
            # Convert Path objects to strings for JSON serialization
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
    # Modern Linux theme (inspired by GNOME/KDE)
    BG = (45, 45, 45)
    SIDEBAR = (35, 35, 35)
    HEADER = (30, 30, 30)
    CARD = (50, 50, 50)
    
    # Accent (Ubuntu orange / Fedora blue style)
    ACCENT = (233, 84, 32)
    ACCENT_HOVER = (253, 104, 52)
    ACCENT_DARK = (213, 64, 12)
    
    # Status colors
    SUCCESS = (119, 178, 85)
    ERROR = (235, 77, 75)
    WARNING = (242, 169, 59)
    
    # Text
    TEXT = (240, 240, 240)
    TEXT_DIM = (160, 160, 160)
    TEXT_DISABLED = (100, 100, 100)
    
    # UI Elements
    BORDER = (70, 70, 70)
    HOVER = (60, 60, 60)
    SELECTED = (55, 55, 65)
    
    # Progress
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
        self.expanded = False  # Start collapsed by default
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
        
        # Smooth scrolling properties
        self.scroll_offset = 0.0  # Current scroll position (float for smooth animation)
        self.target_scroll = 0.0  # Target scroll position
        self.scroll_velocity = 0.0  # Scroll velocity for momentum
        self.max_scroll = 0
        
        self.font = pygame.font.Font(None, 20)
        self.icon_font = pygame.font.Font(None, 18)
        self.row_height = 24
        self.indent = 20
        self.checkbox_size = 16
        self.hover_index = -1
    
    def build_tree(self, root_path, all_files, pre_selected_files=None):
        """Build the file tree structure
        
        Args:
            root_path: Root directory path
            all_files: List of all file paths to include
            pre_selected_files: Optional list of file paths to pre-select
        """
        self.root = TreeNode(root_path, is_folder=True)
        self.root.expanded = True  # Only expand root so we can see first level
        folder_map = {str(root_path): self.root}
        
        # Convert pre-selected files to a set for fast lookup
        pre_selected_set = set()
        if pre_selected_files:
            for p in pre_selected_files:
                if isinstance(p, Path):
                    pre_selected_set.add(str(p))
                else:
                    pre_selected_set.add(str(Path(p)))
        
        # Build folder structure
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
                    # Don't force expanded - let default (False) work
                    parent_node.children.append(new_node)
                    folder_map[folder_key] = new_node
                
                parent_node = folder_map[folder_key]
        
        # Add files with pre-selection
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
            
            # Auto-select if in pre-selected list
            if str(file_path) in pre_selected_set:
                file_node.selected = True
            
            parent_node.children.append(file_node)
        
        # Sort
        def sort_children(node):
            node.children.sort(key=lambda n: (0 if n.is_folder else 1, n.name.lower()))
            for child in node.children:
                if child.is_folder:
                    sort_children(child)
        
        sort_children(self.root)
        self._update_visible_nodes()
    
    def _update_visible_nodes(self):
        """Update the list of visible nodes"""
        self.visible_nodes = []
        
        def add_node(node):
            self.visible_nodes.append(node)
            if node.is_folder and node.expanded:
                for child in node.children:
                    add_node(child)
        
        if self.root:
            for child in self.root.children:
                add_node(child)
        
        # Update max scroll
        total_height = len(self.visible_nodes) * self.row_height
        self.max_scroll = max(0, total_height - self.height)
        
        # Clamp scroll positions
        self.target_scroll = max(0, min(self.target_scroll, self.max_scroll))
        self.scroll_offset = max(0, min(self.scroll_offset, self.max_scroll))
    
    def update(self):
        """Update scroll animation with smooth easing - highly controllable"""
        if abs(self.scroll_offset - self.target_scroll) > 0.5:
            # Smooth scroll animation with controlled easing
            distance = self.target_scroll - self.scroll_offset
            
            # Direct interpolation for precise control (no spring physics)
            # This gives smooth movement without slippery momentum
            self.scroll_offset += distance * 0.22  # Sweet spot for control
            
            # Clamp to valid range
            self.scroll_offset = max(0, min(self.scroll_offset, self.max_scroll))
        else:
            # Snap to target when close enough
            self.scroll_offset = self.target_scroll
            self.scroll_velocity = 0.0
    
    def draw(self, screen):
        # Background
        pygame.draw.rect(screen, Colors.CARD, (self.x, self.y, self.width, self.height))
        pygame.draw.rect(screen, Colors.BORDER, (self.x, self.y, self.width, self.height), 1)
        
        # Clip area
        clip_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        screen.set_clip(clip_rect)
        
        # Calculate starting y position with smooth scrolling
        y = self.y - int(self.scroll_offset)
        
        for idx, node in enumerate(self.visible_nodes):
            # Skip nodes that are above visible area
            if y + self.row_height < self.y:
                y += self.row_height
                continue
            # Stop drawing nodes below visible area
            if y > self.y + self.height:
                break
            
            # Hover background
            row_rect = pygame.Rect(self.x, y, self.width, self.row_height)
            if idx == self.hover_index:
                pygame.draw.rect(screen, Colors.HOVER, row_rect)
            
            # Selection background
            if node.selected:
                pygame.draw.rect(screen, Colors.SELECTED, row_rect)
            
            x_offset = self.x + 8 + (node.depth * self.indent)
            
            # Checkbox
            checkbox_rect = pygame.Rect(x_offset, y + 4, self.checkbox_size, self.checkbox_size)
            pygame.draw.rect(screen, Colors.BORDER, checkbox_rect, 1)
            
            if node.selected:
                # Checkmark
                check_color = Colors.ACCENT
                pygame.draw.rect(screen, check_color, checkbox_rect.inflate(-2, -2))
                # Draw check icon
                check_surf = self.icon_font.render("✓", True, Colors.TEXT)
                screen.blit(check_surf, (x_offset + 2, y + 2))
            
            x_offset += self.checkbox_size + 8
            
            # Icon
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
            
            # Name
            name_color = Colors.TEXT if not node.is_folder else Colors.TEXT
            name_surf = self.font.render(node.name, True, name_color)
            screen.blit(name_surf, (x_offset, y + 4))
            
            y += self.row_height
        
        screen.set_clip(None)
        
        # Scrollbar with smooth position
        total_height = len(self.visible_nodes) * self.row_height
        if total_height > self.height:
            scrollbar_width = 8
            scrollbar_height = max(30, int(self.height * self.height / total_height))
            
            # Use current scroll_offset for smooth scrollbar movement
            scroll_ratio = self.scroll_offset / self.max_scroll if self.max_scroll > 0 else 0
            scrollbar_y = self.y + int(scroll_ratio * (self.height - scrollbar_height))
            
            # Track
            track_rect = pygame.Rect(self.x + self.width - scrollbar_width - 2, self.y + 2, 
                                    scrollbar_width, self.height - 4)
            pygame.draw.rect(screen, Colors.PROGRESS_TRACK, track_rect, border_radius=4)
            
            # Thumb
            thumb_rect = pygame.Rect(self.x + self.width - scrollbar_width - 2, scrollbar_y,
                                    scrollbar_width, scrollbar_height)
            pygame.draw.rect(screen, Colors.ACCENT, thumb_rect, border_radius=4)
    
    def handle_click(self, pos):
        if not (self.x <= pos[0] <= self.x + self.width and
                self.y <= pos[1] <= self.y + self.height):
            return

        # Calculate which node was clicked using current scroll offset
        y = self.y - int(self.scroll_offset)
        for node in self.visible_nodes:
            if y <= pos[1] < y + self.row_height:
                x_offset = self.x + 8 + (node.depth * self.indent)

                # Click on arrow
                if node.is_folder and pos[0] < x_offset + 16:
                    node.toggle_expand()
                    self._update_visible_nodes()
                # Click on checkbox
                elif pos[0] >= x_offset + 16 and pos[0] < x_offset + 16 + self.checkbox_size + 8:
                    node.toggle_select()
                # Click on folder name (expand/collapse)
                elif node.is_folder:
                    node.toggle_expand()
                    self._update_visible_nodes()
                # Click on file name (select)
                else:
                    node.toggle_select()
                return

            y += self.row_height
    
    def handle_motion(self, pos):
        if not (self.x <= pos[0] <= self.x + self.width and 
                self.y <= pos[1] <= self.y + self.height):
            self.hover_index = -1
            return
        
        # Calculate which node is being hovered using current scroll offset
        y = self.y - int(self.scroll_offset)
        for idx, node in enumerate(self.visible_nodes):
            if y <= pos[1] < y + self.row_height:
                self.hover_index = idx
                return
            y += self.row_height
        self.hover_index = -1
    
    def handle_scroll(self, delta):
        """Handle scroll wheel with smooth but controlled animation
        
        Args:
            delta: Scroll amount in pixels (positive = scroll down, negative = scroll up)
        """
        # Update target scroll position (no momentum, just direct control)
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
        
        # Header
        self.header_height = 50
        
        # Tree
        tree_y = self.y + self.header_height + 50
        self.tree = FileTreeView(
            self.x + 10,
            tree_y,
            self.width - 20,
            self.height - self.header_height - 120
        )
        # Build tree with pre-selected files
        self.tree.build_tree(root_path, all_files, pre_selected_files)
        
        # Buttons
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
        # Overlay
        overlay = pygame.Surface((800, 600), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        
        # Dialog background
        pygame.draw.rect(self.screen, Colors.CARD, (self.x, self.y, self.width, self.height))
        pygame.draw.rect(self.screen, Colors.BORDER, (self.x, self.y, self.width, self.height), 1)
        
        # Header
        header_rect = pygame.Rect(self.x, self.y, self.width, self.header_height)
        pygame.draw.rect(self.screen, Colors.HEADER, header_rect)
        pygame.draw.line(self.screen, Colors.BORDER, 
                        (self.x, self.y + self.header_height),
                        (self.x + self.width, self.y + self.header_height))
        
        # Title
        title_surf = self.title_font.render("Select Files to Upload", True, Colors.TEXT)
        title_rect = title_surf.get_rect(midleft=(self.x + 20, self.y + self.header_height // 2))
        self.screen.blit(title_surf, title_rect)
        
        # File count
        selected_count = len(self.tree.get_selected_files())
        total_files = sum(1 for node in self.tree.visible_nodes if not node.is_folder)
        
        count_text = f"{selected_count} / {total_files} selected"
        count_surf = self.font.render(count_text, True, Colors.TEXT_DIM)
        count_rect = count_surf.get_rect(center=(self.x + self.width // 2, 
                                                  self.y + self.header_height + 25))
        self.screen.blit(count_surf, count_rect)
        
        # Memory indicator
        if SelectionMemory.has_selections():
            memory_text = " "
            memory_surf = self.font.render(memory_text, True, Colors.ACCENT)
            memory_rect = memory_surf.get_rect(midright=(self.x + self.width - 20,
                                                         self.y + self.header_height + 25))
            self.screen.blit(memory_surf, memory_rect)
        
        # Tree
        self.tree.draw(self.screen)
        
        # Buttons
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
        self.ser.write(b"\x03\x03")
        self._wait_ready(0.2)
        self.ser.write(b"\x01")
        self._wait_ready(0.2)
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
    
    def mkdir(self, path):
        self._exec_capture(f"""
import os
try:
    os.mkdir("{path}")
except OSError:
    pass
""")
    
    def put(self, local: Path, remote: str):
        """Upload file to device using chunked write to avoid MemoryError"""
        CHUNK_SIZE = 128  # Small chunks for memory-constrained devices
        
        data = local.read_bytes()
        total_len = len(data)
        num_chunks = (total_len + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        # Use raw REPL mode for file operations (like ampy)
        self.ser.write(b"\x01")  # Enter raw REPL
        self._wait_ready(3)
        
        # Send the file write code with chunked writing
        code = f"""
import os
try:
    os.remove("{remote}")
except OSError:
    pass

with open("{remote}", "wb") as f:
"""
        self.ser.write(code.encode())
        self._wait_ready(0.05)
        
        # Send each chunk as individual write
        for i in range(num_chunks):
            chunk = data[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE]
            chunk_code = f"    f.write({repr(chunk)})\n"
            self.ser.write(chunk_code.encode())
            self._wait_ready(0.02)  # Brief pause between chunks
        
        # Execute the accumulated code
        self.ser.write(b"\x04")
        self._wait_ready(0.2)

        # Read any output
        if self.ser.in_waiting:
            output = self.ser.read(self.ser.in_waiting)
            if b"Traceback" in output:
                raise MicroPyError(output.decode(errors="ignore"))

        # Exit raw REPL
        self.ser.write(b"\x02")
        self._wait_ready(0.1)
    
    def ensure_dirs(self, remote_path: str):
        parts = remote_path.split("/")[:-1]
        cur = ""
        for p in parts:
            cur = f"{cur}/{p}" if cur else p
            self.mkdir(cur)
    
    def exit_raw_repl(self):
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
        # Checkbox
        pygame.draw.rect(screen, Colors.BORDER, self.rect, 1)
        if self.checked:
            pygame.draw.rect(screen, Colors.ACCENT, self.rect.inflate(-2, -2))
            check_surf = self.font.render("✓", True, Colors.TEXT)
            screen.blit(check_surf, (self.rect.x + 2, self.rect.y))
        
        # Text
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
        """Update progress animation - smooth and controllable"""
        if abs(self.progress - self.target_progress) > 0.001:
            distance = self.target_progress - self.progress
            self.progress += distance * 0.22  # Smooth and controllable
        else:
            self.progress = self.target_progress
    
    def draw(self, screen):
        # Background
        pygame.draw.rect(screen, Colors.PROGRESS_TRACK, self.rect, border_radius=3)
        
        # Progress
        if self.progress > 0:
            fill_rect = self.rect.copy()
            fill_rect.width = int(self.rect.width * self.progress)
            pygame.draw.rect(screen, Colors.ACCENT, fill_rect, border_radius=3)
        
        # Border
        pygame.draw.rect(screen, Colors.BORDER, self.rect, 1, border_radius=3)
        
        # Percentage
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
        
        # Auto-scroll to bottom
        total_height = len(self.entries) * 20
        max_scroll = max(0, total_height - self.rect.height + 10)
        self.target_scroll = max_scroll
    
    def update(self):
        """Update scroll animation - highly controllable"""
        if abs(self.scroll_offset - self.target_scroll) > 0.5:
            distance = self.target_scroll - self.scroll_offset
            self.scroll_offset += distance * 0.22  # Smooth and controllable
        else:
            self.scroll_offset = self.target_scroll
    
    def draw(self, screen):
        # Background
        pygame.draw.rect(screen, Colors.CARD, self.rect)
        pygame.draw.rect(screen, Colors.BORDER, self.rect, 1)
        
        # Clip
        screen.set_clip(self.rect.inflate(-4, -4))
        
        y = self.rect.y + 5 - self.scroll_offset
        
        for timestamp, message, msg_type in self.entries:
            if y + 20 < self.rect.y:
                y += 20
                continue
            if y > self.rect.y + self.rect.height:
                break
            
            # Timestamp
            time_surf = self.time_font.render(f"[{timestamp}]", True, Colors.TEXT_DIM)
            screen.blit(time_surf, (self.rect.x + 8, y))
            
            # Message
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
        
        # Scrollbar
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
        
        # Fonts
        self.title_font = pygame.font.Font(None, 32)
        self.font = pygame.font.Font(None, 20)
        
        # Header
        self.header_height = 60
        
        # Buttons
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
        
        # Progress bar
        progress_y = start_y + (button_height + button_spacing) * 3 + 20
        self.progress_bar = LinuxProgressBar(50, progress_y, self.width - 100, 25)
        
        # Auto-retry checkbox
        self.auto_retry_checkbox = LinuxCheckbox(50, progress_y + 35, "Auto-retry on failure (hard reset + 5s wait)", checked=True)
        
        # Log panel
        log_y = progress_y + 70
        self.log_panel = LogPanel(20, log_y, self.width - 40, self.height - log_y - 20)
        
        # State
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
        # Background
        self.screen.fill(Colors.BG)
        
        # Header
        header_rect = pygame.Rect(0, 0, self.width, self.header_height)
        pygame.draw.rect(self.screen, Colors.HEADER, header_rect)
        pygame.draw.line(self.screen, Colors.BORDER, (0, self.header_height), 
                        (self.width, self.header_height))
        
        # Title
        title_surf = self.title_font.render("CalSci Flasher", True, Colors.TEXT)
        title_rect = title_surf.get_rect(midleft=(20, self.header_height // 2))
        self.screen.blit(title_surf, title_rect)
        
        # Subtitle
        subtitle = self.font.render("ESP32 MicroPython Tool", True, Colors.TEXT_DIM)
        self.screen.blit(subtitle, (20, self.header_height // 2 + 15))
        
        # Buttons
        self.update_btn.draw(self.screen)
        self.flash_btn.draw(self.screen)
        self.upload_btn.draw(self.screen)
        
        # Progress
        self.progress_bar.update()
        self.progress_bar.draw(self.screen)
        
        # Auto-retry checkbox
        self.auto_retry_checkbox.draw(self.screen)
        
        # Log
        self.log_panel.update()
        self.log_panel.draw(self.screen)
        
        # Dialog
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
                
                try:
                    # Try upload with optional hard reset retry
                    success = False
                    for attempt in range(2):
                        try:
                            flasher.ensure_dirs(remote_path)
                            flasher.put(path, remote_path)
                            success = True
                            break
                        except Exception as e:
                            if attempt == 0 and auto_retry:
                                self.log(f"Upload failed: {path.name}, retrying after hard reset...", "warning")
                                # Hard reset and wait
                                flasher.ser.dtr = False
                                flasher.ser.rts = True
                                time.sleep(0.1)
                                flasher.ser.dtr = True
                                flasher.ser.rts = False
                                time.sleep(0.1)
                                flasher.ser.close()
                                time.sleep(5)
                                flasher = MicroPyFlasher(port)
                            else:
                                raise e
                    
                    if success:
                        uploaded += path.stat().st_size
                        progress = 0.05 + (uploaded / total_size) * 0.95
                        self.progress_bar.set_progress(progress)
                        self.log(f"[{i}/{len(files)}] {path.name}", "info")
                    else:
                        failed_files.append(path.name)
                        
                except Exception as e:
                    # Individual file failure - skip to next file
                    failed_files.append(path.name)
                    self.log(f"Skipping failed file: {path.name}", "warning")
                    continue  # Continue to next file
            
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
        
        # Load previously selected files
        pre_selected = SelectionMemory.load_selections()
        if pre_selected:
            self.log(f"Loaded {len(pre_selected)} previous selections", "info")
        
        self.selection_dialog = FileSelectionDialog(self.screen, files, ROOT, pre_selected)
        
        # Dialog loop
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
            
            # Redraw
            self.draw()
            clock.tick(60)
        
        # Get result
        result = self.selection_dialog.result
        selected_files = self.selection_dialog.get_selected_files()
        
        self.selection_dialog = None
        
        if result == "cancel" or not selected_files:
            if result == "cancel":
                self.log("Upload cancelled", "info")
            else:
                self.log("No files selected", "info")
            return
        
        # Result is "upload" - proceed with selected files
        self.log(f"Selected {len(selected_files)} files for upload", "info")
        
        # Save selections for future use
        SelectionMemory.save_selections(selected_files)
        self.log(f"Saved {len(selected_files)} selections", "info")
        
        # Upload in thread
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
                    
                    try:
                        # Try upload with optional hard reset retry
                        success = False
                        for attempt in range(2):  # Max 2 attempts (initial + 1 retry)
                            try:
                                flasher.ensure_dirs(remote_path)
                                flasher.put(path, remote_path)
                                success = True
                                break
                            except Exception as e:
                                if attempt == 0 and auto_retry:
                                    self.log(f"Upload failed: {path.name}, retrying after hard reset...", "warning")
                                    # Hard reset and wait
                                    flasher.ser.dtr = False
                                    flasher.ser.rts = True
                                    time.sleep(0.1)
                                    flasher.ser.dtr = True
                                    flasher.ser.rts = False
                                    time.sleep(0.1)
                                    flasher.ser.close()
                                    time.sleep(5)  # Wait 5 seconds for device to reboot
                                    flasher = MicroPyFlasher(port)
                                else:
                                    # On second attempt or retry disabled, raise to outer except
                                    raise e
                        
                        if success:
                            uploaded += path.stat().st_size
                            progress = 0.1 + (uploaded / total_size) * 0.9
                            self.progress_bar.set_progress(progress)
                            self.log(f"[{i}/{len(selected_files)}] {path.name}", "info")
                        else:
                            failed_files.append(path.name)
                            
                    except Exception as e:
                        # Individual file failure - skip to next file
                        failed_files.append(path.name)
                        self.log(f"Skipping failed file: {path.name}", "warning")
                        continue  # Continue to next file
                
                flasher.exit_raw_repl()
                flasher.close()
                
                if failed_files:
                    self.log(f"Upload complete with {len(failed_files)} failures: {', '.join(failed_files)}", "warning")
                else:
                    self.log("Upload complete!", "success")
                    self.progress_bar.set_progress(1.0)
                
                # Keep selections saved for future uploads
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
                    if event.button == 4:  # Scroll up
                        if not self.selection_dialog:
                            self.log_panel.handle_scroll(-40)
                    elif event.button == 5:  # Scroll down
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
                            pass  # Toggle handled in handle_click
                        elif self.update_btn.handle_click(event.pos):
                            threading.Thread(target=self.handle_update, daemon=True).start()
                        elif self.flash_btn.handle_click(event.pos):
                            threading.Thread(target=self.handle_flash, daemon=True).start()
                        elif self.upload_btn.handle_click(event.pos):
                            self.handle_upload_selected()
            
            self.draw()
            self.clock.tick(60)
        
        pygame.quit()


# ---------- ENTRY POINT ----------

def main():
    app = CalSciApp()
    app.run()

if __name__ == "__main__":
    main()