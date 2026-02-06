"""
CalSci Flasher - Dialog Modules
Contains all dialog windows for file selection and deletion.
"""

from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTreeWidget, QTreeWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


# ============================================================
# ================= FILE SELECTION DIALOG =====================
# ============================================================

class FileSelectionDialog(QDialog):
    """Dialog for selecting files to upload from local repository."""
    
    def __init__(self, all_files, root_path, pre_selected_files=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Files to Upload")
        self.setMinimumSize(720, 560)
        self.root_path = root_path
        self.all_files = all_files
        self.pre_selected = set(str(p) for p in (pre_selected_files or []))

        self._build_ui()
        self._populate_tree()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("color: #a0a0a0; font-size: 13px;")
        layout.addWidget(self.info_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Size"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setRootIsDecorated(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(22)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #2d2d2d;
                color: #e8e8e8;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                font-size: 13px;
            }
            QTreeWidget::item {
                padding: 5px 4px;
                border-bottom: 1px solid #333333;
            }
            QTreeWidget::item:hover {
                background-color: #383838;
            }
            QTreeWidget::item:selected {
                background-color: #3a4a5a;
                color: #ffffff;
            }
            QTreeWidget::branch:has-siblings:!adjoins-item {
                border-image: none;
                border-left: 1px solid #4a4a4a;
            }
            QTreeWidget::branch:!has-siblings:!adjoins-item {
                border-image: none;
            }
            QHeaderView::section {
                background-color: #1e1e1e;
                color: #a0a0a0;
                border: none;
                border-bottom: 1px solid #3a3a3a;
                padding: 6px 8px;
                font-weight: 500;
                font-size: 12px;
            }
        """)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.select_all_btn = QPushButton("☑  Select All")
        self.deselect_all_btn = QPushButton("☐  Deselect All")
        self.upload_btn = QPushButton("⬆  Upload")
        self.cancel_btn = QPushButton("Cancel")

        for btn in [self.select_all_btn, self.deselect_all_btn, self.cancel_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(233, 84, 32, 0.5);
                    color: #ffffff;
                    border: 1px solid rgba(233, 84, 32, 0.8);
                    border-radius: 5px;
                    padding: 8px 18px;
                    font-size: 13px;
                }
                QPushButton:hover { background-color: rgba(233, 84, 32, 0.7); }
                QPushButton:pressed { background-color: rgba(233, 84, 32, 0.9); }
            """)

        self.upload_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 5px;
                padding: 8px 22px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: rgba(233, 84, 32, 0.7); }
            QPushButton:pressed { background-color: rgba(233, 84, 32, 0.9); }
            QPushButton:disabled { background-color: rgba(85, 85, 85, 0.5); color: #777777; border-color: rgba(85, 85, 85, 0.8); }
        """)

        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.upload_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self.select_all_btn.clicked.connect(self._select_all)
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        self.upload_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self._update_upload_btn_text()

    def _populate_tree(self):
        self.tree.setUpdatesEnabled(False)
        folder_map = {}

        sorted_files = sorted(self.all_files, key=lambda p: (str(p.parent), p.name))

        for file_path in sorted_files:
            rel = file_path.relative_to(self.root_path)
            parts = list(rel.parts)

            parent_item = None

            for i in range(len(parts) - 1):
                folder_key = str(Path(*parts[: i + 1]))
                if folder_key not in folder_map:
                    folder_item = QTreeWidgetItem()
                    folder_item.setText(0, parts[i])
                    folder_item.setText(1, "")
                    folder_item.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                        | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsAutoTristate
                    )
                    folder_item.setCheckState(0, Qt.CheckState.Unchecked)
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, None)
                    folder_item.setForeground(0, QColor("#e95420"))

                    if parent_item is None:
                        self.tree.addTopLevelItem(folder_item)
                    else:
                        parent_item.addChild(folder_item)
                        parent_item.setExpanded(False)

                    folder_map[folder_key] = folder_item
                    folder_item.setExpanded(False)

                parent_item = folder_map[folder_key]

            file_item = QTreeWidgetItem()
            file_item.setText(0, parts[-1])

            size_bytes = file_path.stat().st_size
            file_item.setText(1, self._format_size(size_bytes))

            file_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )

            if str(file_path) in self.pre_selected:
                file_item.setCheckState(0, Qt.CheckState.Checked)
            else:
                file_item.setCheckState(0, Qt.CheckState.Unchecked)

            file_item.setData(0, Qt.ItemDataRole.UserRole, str(file_path))
            file_item.setForeground(0, QColor("#d0d0d0"))

            if parent_item is None:
                self.tree.addTopLevelItem(file_item)
            else:
                parent_item.addChild(file_item)

        self.tree.collapseAll()
        self.tree.setUpdatesEnabled(True)
        self._update_upload_btn_text()

    def _on_item_clicked(self, item, column):
        if item.childCount() > 0:
            item.setExpanded(not item.isExpanded())

    def _on_item_changed(self, item, column):
        if column == 0:
            self._update_upload_btn_text()

    def _select_all(self):
        self._set_all_check(Qt.CheckState.Checked)

    def _deselect_all(self):
        self._set_all_check(Qt.CheckState.Unchecked)

    def _set_all_check(self, state):
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            self._set_recursive(item, state)
        self.tree.blockSignals(False)
        self._update_upload_btn_text()

    def _set_recursive(self, item, state):
        item.setCheckState(0, state)
        for i in range(item.childCount()):
            self._set_recursive(item.child(i), state)

    def _update_upload_btn_text(self):
        count = len(self.get_selected_files())
        if count > 0:
            self.upload_btn.setText(f"⬆  Upload ({count})")
            self.upload_btn.setEnabled(True)
        else:
            self.upload_btn.setText("⬆  Upload")
            self.upload_btn.setEnabled(False)
        self.info_label.setText(f"{count} / {len(self.all_files)} files selected")

    def get_selected_files(self):
        selected = []
        self._collect_checked(self.tree.invisibleRootItem(), selected)
        return selected

    def _collect_checked(self, item, result):
        for i in range(item.childCount()):
            child = item.child(i)
            path_str = child.data(0, Qt.ItemDataRole.UserRole)
            if path_str is not None:
                if child.checkState(0) == Qt.CheckState.Checked:
                    result.append(Path(path_str))
            self._collect_checked(child, result)

    @staticmethod
    def _format_size(size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"


# ============================================================
# ================= CalSci FILE SELECTION DIALOG ==============
# ============================================================

class ESP32FileSelectionDialog(QDialog):
    """Dialog for selecting files/folders from CalSci to delete."""

    def __init__(self, esp32_files, esp32_dirs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Files/Folders to Delete")
        self.setMinimumSize(720, 560)
        self.esp32_files = esp32_files
        self.esp32_dirs = esp32_dirs

        self._build_ui()
        self._populate_tree()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("color: #e74c3c; font-size: 13px; font-weight: 600;")
        layout.addWidget(self.info_label)

        warning_label = QLabel("⚠️ Selected items will be PERMANENTLY DELETED from CalSci")
        warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning_label.setStyleSheet("color: #f39c12; font-size: 12px; margin-bottom: 8px;")
        layout.addWidget(warning_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Type"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setRootIsDecorated(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(22)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #2d2d2d;
                color: #e8e8e8;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                font-size: 13px;
            }
            QTreeWidget::item {
                padding: 5px 4px;
                border-bottom: 1px solid #333333;
            }
            QTreeWidget::item:hover {
                background-color: #383838;
            }
            QTreeWidget::item:selected {
                background-color: #5a3a3a;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #1e1e1e;
                color: #a0a0a0;
                border: none;
                border-bottom: 1px solid #3a3a3a;
                padding: 6px 8px;
                font-weight: 500;
                font-size: 12px;
            }
        """)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.select_all_btn = QPushButton("☑  Select All")
        self.deselect_all_btn = QPushButton("☐  Deselect All")
        self.delete_btn = QPushButton("🗑️  Delete Selected")
        self.cancel_btn = QPushButton("Cancel")

        for btn in [self.select_all_btn, self.deselect_all_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(233, 84, 32, 0.5);
                    color: #ffffff;
                    border: 1px solid rgba(233, 84, 32, 0.8);
                    border-radius: 5px;
                    padding: 8px 18px;
                    font-size: 13px;
                }
                QPushButton:hover { background-color: rgba(233, 84, 32, 0.7); }
                QPushButton:pressed { background-color: rgba(233, 84, 32, 0.9); }
            """)

        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 5px;
                padding: 8px 22px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: rgba(233, 84, 32, 0.7); }
            QPushButton:pressed { background-color: rgba(233, 84, 32, 0.9); }
            QPushButton:disabled { background-color: rgba(85, 85, 85, 0.5); color: #777777; border-color: rgba(85, 85, 85, 0.8); }
        """)

        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(233, 84, 32, 0.5);
                color: #ffffff;
                border: 1px solid rgba(233, 84, 32, 0.8);
                border-radius: 5px;
                padding: 8px 18px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: rgba(233, 84, 32, 0.7); }
            QPushButton:pressed { background-color: rgba(233, 84, 32, 0.9); }
        """)

        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self.select_all_btn.clicked.connect(self._select_all)
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        self.delete_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self._update_delete_btn_text()

    def _populate_tree(self):
        self.tree.setUpdatesEnabled(False)
        folder_map = {}

        for file_path in sorted(self.esp32_files):
            parts = file_path.strip("/").split("/")
            parent_item = None

            for i in range(len(parts) - 1):
                folder_key = "/".join(parts[: i + 1])
                if folder_key not in folder_map:
                    folder_item = QTreeWidgetItem()
                    folder_item.setText(0, parts[i])
                    folder_item.setText(1, "")
                    folder_item.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                        | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsAutoTristate
                    )
                    folder_item.setCheckState(0, Qt.CheckState.Unchecked)
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, ("/" + folder_key, "folder"))
                    folder_item.setForeground(0, QColor("#e95420"))

                    if parent_item is None:
                        self.tree.addTopLevelItem(folder_item)
                    else:
                        parent_item.addChild(folder_item)

                    folder_map[folder_key] = folder_item
                    folder_item.setExpanded(False)

                parent_item = folder_map[folder_key]

            file_item = QTreeWidgetItem()
            file_item.setText(0, parts[-1])
            file_item.setText(1, "")
            file_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            file_item.setCheckState(0, Qt.CheckState.Unchecked)
            file_item.setData(0, Qt.ItemDataRole.UserRole, (file_path, "file"))
            file_item.setForeground(0, QColor("#d0d0d0"))

            if parent_item is None:
                self.tree.addTopLevelItem(file_item)
            else:
                parent_item.addChild(file_item)

        self._sort_children(self.tree.invisibleRootItem())

        self.tree.collapseAll()
        self.tree.setUpdatesEnabled(True)
        self._update_delete_btn_text()

    def _sort_children(self, parent_item):
        child_count = parent_item.childCount()
        if child_count == 0:
            return

        children = []
        for i in range(child_count):
            children.append(parent_item.takeChild(0))

        files   = [c for c in children if c.childCount() == 0]
        folders = [c for c in children if c.childCount() > 0]

        files.sort(key=lambda c: c.text(0).lower())
        folders.sort(key=lambda c: c.text(0).lower())

        for item in files + folders:
            if isinstance(parent_item, QTreeWidget):
                parent_item.addTopLevelItem(item)
            else:
                parent_item.addChild(item)

        for folder in folders:
            self._sort_children(folder)

    def _on_item_clicked(self, item, column):
        if item.childCount() > 0:
            item.setExpanded(not item.isExpanded())

    def _on_item_changed(self, item, column):
        if column == 0:
            self._update_delete_btn_text()

    def _select_all(self):
        self._set_all_check(Qt.CheckState.Checked)

    def _deselect_all(self):
        self._set_all_check(Qt.CheckState.Unchecked)

    def _set_all_check(self, state):
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            self._set_recursive(item, state)
        self.tree.blockSignals(False)
        self._update_delete_btn_text()

    def _set_recursive(self, item, state):
        item.setCheckState(0, state)
        for i in range(item.childCount()):
            self._set_recursive(item.child(i), state)

    def _update_delete_btn_text(self):
        count = len(self.get_selected_items())
        if count > 0:
            self.delete_btn.setText(f"🗑️  Delete ({count})")
            self.delete_btn.setEnabled(True)
        else:
            self.delete_btn.setText("🗑️  Delete Selected")
            self.delete_btn.setEnabled(False)
        self.info_label.setText(f"{count} item(s) selected for deletion")

    def get_selected_items(self):
        selected = []
        self._collect_checked(self.tree.invisibleRootItem(), selected)
        return selected

    def _collect_checked(self, item, result):
        for i in range(item.childCount()):
            child = item.child(i)
            data = child.data(0, Qt.ItemDataRole.UserRole)
            if data is not None:
                path_str, item_type = data
                if child.checkState(0) == Qt.CheckState.Checked:
                    result.append((path_str, item_type))
            self._collect_checked(child, result)
