# Helper widgets and file I/O used by the main menu actions.
# - CustomizationDialog: lets the user assign a unique color to each of the 10
#   climbers (named presets or a picked/custom color). Emits colors_preview on
#   every change (for live preview) and colors_changed on Apply.
# - InitialFillDialog: set the starting height of every climber (0-11 levels).
# - FileManager: save/open JSON files for simulation settings.

import json
import os
import random
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap, QIcon
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QPushButton, QLabel,
    QComboBox, QDialog, QColorDialog, QFileDialog, QMessageBox, QSpinBox,
)

NUM_CLIMBERS = 10

DEFAULT_PALETTE = [
    "#E63946", "#F4A261", "#E9C46A", "#2A9D8F", "#264653",
    "#A8DADC", "#457B9D", "#1D3557", "#9B5DE5", "#F15BB5"
]

DEFAULT_FILE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COLOR_MAP = {
    "Red": "#E63946",
    "Orange": "#F4A261",
    "Yellow": "#E9C46A",
    "Green": "#2A9D8F",
    "Dark Blue": "#264653",
    "Light Blue": "#A8DADC",
    "Blue": "#457B9D",
    "Brown": "#964B00",
    "Purple": "#9B5DE5",
    "Pink": "#F15BB5",
    "Maroon": "#800000",
    "Olive": "#808000",
    "Navy": "#000080",
    "Lime": "#A3E635",
    "Teal": "#008080",
    "Gold": "#DAA520",
}


class CustomizationDialog(QDialog):
    # Color picker for the 10 climbers, with duplicate rejection and live
    # preview while the user changes a selection.

    colors_changed = pyqtSignal(list)
    colors_preview = pyqtSignal(list)

    def __init__(self, parent=None, current_colors=None):
        super().__init__(parent)
        self.setWindowTitle("Climber Color Customization")
        self.resize(380, 480)

        # Working copy of the current colors; starts from the passed palette
        self.current_colors = list(current_colors) if current_colors else list(DEFAULT_PALETTE)
        self.preset_colors = list(COLOR_MAP.keys())

        self._init_ui()

    def _create_color_icon(self, color_hex):
        # Make a small 16x16 swatch icon so colors are visible in the combo boxes
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(color_hex))
        return QIcon(pixmap)

    def _init_ui(self):
        dialog_layout = QVBoxLayout(self)
        grid_layout = QGridLayout()

        self.combo_boxes = []

        # Build one combo box per climber with all named presets + "Custom..."
        for i in range(NUM_CLIMBERS):
            label = QLabel(f"Climber {i + 1}:")
            combo = QComboBox()

            for name in self.preset_colors:
                hex_code = COLOR_MAP.get(name, self.current_colors[i])
                combo.blockSignals(True)
                combo.addItem(self._create_color_icon(hex_code), name)
                combo.blockSignals(False)

            # Preselect the item that matches the climber's actual current color
            combo.blockSignals(True)
            combo.setCurrentIndex(self._index_for_color(self.current_colors[i]))
            combo.setItemIcon(combo.currentIndex(), self._create_color_icon(self.current_colors[i]))
            combo.blockSignals(False)

            combo.currentIndexChanged.connect(
                lambda idx, c=combo, climber_idx=i: self._handle_color_change(climber_idx, c)
            )

            self.combo_boxes.append(combo)

            # Arrange climbers in a 5x2 grid inside the dialog
            row = i % 5
            col = (i // 5) * 2
            grid_layout.addWidget(label, row, col)
            grid_layout.addWidget(combo, row, col + 1)

        dialog_layout.addLayout(grid_layout)
        dialog_layout.addSpacing(15)

        # Action Buttons: Close, Random, OK
        btn_box = QHBoxLayout()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        btn_random = QPushButton("Random")
        btn_random.clicked.connect(self.randomize_colors)
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self._on_apply)

        btn_box.addWidget(btn_close)
        btn_box.addWidget(btn_random)
        btn_box.addWidget(btn_ok)
        dialog_layout.addLayout(btn_box)

    def _handle_color_change(self, index, combo):
        selected_text = combo.currentText()
        if selected_text in COLOR_MAP:
            hex_val = COLOR_MAP[selected_text]
        else:
            return

        # Colors must be unique across all climbers
        duplicate = self._find_duplicate(hex_val, index)
        if duplicate is not None:
            self._show_duplicate_warning(hex_val, duplicate)
            self._restore_combo(combo, index)
            return

        self.current_colors[index] = hex_val
        combo.setItemIcon(combo.currentIndex(), self._create_color_icon(hex_val))
        self.colors_preview.emit(self.current_colors)

    def _find_duplicate(self, color_hex, exclude_index):
        # Return the index of another climber already using this color, else None
        for i, existing in enumerate(self.current_colors):
            if i != exclude_index and existing.lower() == color_hex.lower():
                return i
        return None

    def _index_for_color(self, color_hex):
        # Map a hex color back to its combo-box item index.
        for idx, name in enumerate(COLOR_MAP.keys()):
            if COLOR_MAP[name].lower() == color_hex.lower():
                return idx
        return len(self.preset_colors) - 1

    def _restore_combo(self, combo, climber_index):
        # Reset a combo box to the climber's previous color without re-triggering
        idx = self._index_for_color(self.current_colors[climber_index])
        combo.blockSignals(True)
        combo.setCurrentIndex(idx)
        combo.setItemIcon(idx, self._create_color_icon(self.current_colors[climber_index]))
        combo.blockSignals(False)

    def _show_duplicate_warning(self, color_hex, duplicate_index):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Duplicate Color")
        msg.setText(
            f"Color {color_hex} is already used by Climber {duplicate_index + 1}.\n"
            "Each climber must have a unique color."
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setModal(True)
        QTimer.singleShot(500, msg.accept)
        msg.exec()

    def _on_apply(self):
        self.colors_changed.emit(self.current_colors)
        self.accept()

    def randomize_colors(self):
        # Pick a fresh set of unique colors from the named presets.
        self.current_colors = random.sample(list(COLOR_MAP.values()), NUM_CLIMBERS)
        for i, combo in enumerate(self.combo_boxes):
            idx = self._index_for_color(self.current_colors[i])
            combo.blockSignals(True)
            combo.setCurrentIndex(idx)
            combo.setItemIcon(idx, self._create_color_icon(self.current_colors[i]))
            combo.blockSignals(False)
        self.colors_preview.emit(self.current_colors)


class InitialFillDialog(QDialog):
    # Lets the user choose the starting height (0-11) of every climber.

    def __init__(self, current_heights, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Initial Climber Heights")
        self.setModal(True)

        self.height_spins = []

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        for i in range(NUM_CLIMBERS):
            label = QLabel(f"Climber {i + 1}:")
            spin = QSpinBox()
            spin.setRange(0, 11)
            spin.setWrapping(True)
            spin.setValue(current_heights[i] if i < len(current_heights) else 0)
            form_layout.addRow(label, spin)
            self.height_spins.append(spin)

        layout.addLayout(form_layout)

        button_layout = QHBoxLayout()
        random_button = QPushButton("Random")
        reset_button = QPushButton("Reset")
        cancel_button = QPushButton("Cancel")
        ok_button = QPushButton("OK")
        button_layout.addWidget(random_button)
        button_layout.addWidget(reset_button)
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)
        layout.addLayout(button_layout)

        random_button.clicked.connect(self.randomize_values)
        reset_button.clicked.connect(self.reset_values)
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)

    def get_values(self):
        return [spin.value() for spin in self.height_spins]

    def randomize_values(self):
        import random
        for spin in self.height_spins:
            spin.setValue(random.randrange(12))

    def reset_values(self):
        for spin in self.height_spins:
            spin.setValue(0)


class FileManager:
    # Handles reading and writing simulation settings as JSON files.

    @staticmethod
    def open_file(parent=None):
        # Show an open-file dialog; return the parsed JSON dict or None.
        file_path, _ = QFileDialog.getOpenFileName(
            parent, "Open Simulation File", DEFAULT_FILE_DIR,
            "JSON Files (*.json);;All Files (*)"
        )
        if not file_path:
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            QMessageBox.critical(parent, "Error", f"Failed to open file:\n{str(e)}")
            return None

    @staticmethod
    def save_file(data, parent=None):
        """Displays save file dialog and writes provided data to disk."""
        file_path, _ = QFileDialog.getSaveFileName(
            parent, "Save Simulation File", DEFAULT_FILE_DIR,
            "JSON Files (*.json);;All Files (*)"
        )
        if not file_path:
            return False

        # Make sure the file ends with .json even if the user omitted it
        if not file_path.endswith(".json"):
            file_path += ".json"

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            QMessageBox.critical(parent, "Error", f"Failed to save file:\n{str(e)}")
            return False