# GUI layer: the main window and all its wiring.
# - Builds the menu bar, a single shared wall showing all climbers at once, and
#   the bottom control bar (speed + alarm probability, transport buttons).
# - Connects controls to the climber Simulation model.
#   - Handles save/open of settings via FileManager, free-form numeric fields
#   (values are rounded to the closest integer with a 0.5s flash warning,
#   then the box is updated to the rounded number), the status bar, settings
#   persistence.

import json
import math
import os

from PyQt6.QtCore import Qt, QDir, QStandardPaths, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication, QDialog, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)

from animation import Simulation, ClimberWallWidget
from menu_actions import (
    CustomizationDialog, FileManager, InitialFillDialog, DEFAULT_PALETTE,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.climber_colors = list(DEFAULT_PALETTE)
        self.simulation = Simulation()

        self.wall_widget = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.simulation_step)

        self.simulation_finished = False

        self.setup_ui()
        self.setup_menus()
        self.update_ui()
        self.load_settings()

    # ---- Simulation transport ----

    def start_stop_simulation(self):
        if self.simulation.is_running:
            self.simulation.is_running = False
            self.simulation.reset()
            self.wall_widget.reset_animation()
            self.simulation_finished = False
            self.btn_start_stop.setText("Start")
            self.btn_pause_continue.setText("Pause")
            self.timer.stop()
        else:
            self.simulation.reset()
            self.wall_widget.reset_animation()
            self.simulation.is_running = True
            self.simulation_finished = False
            self.btn_start_stop.setText("Stop")
            self.btn_pause_continue.setText(
                "Continue" if self.simulation.is_paused else "Pause")
            if (not self.simulation.is_paused and self.slider_speed.value() > 0):
                self.timer.start(1000 // self.slider_speed.value())
        self.update_ui()

    def pause_continue_simulation(self):
        if self.simulation.is_paused:
            self.simulation.is_paused = False
            self.btn_pause_continue.setText("Pause")
            if self.slider_speed.value() > 0:
                self.timer.start(1000 // self.slider_speed.value())
        else:
            self.simulation.is_paused = True
            self.btn_pause_continue.setText("Continue")
            self.timer.stop()

    def exit_application(self):
        self.save_settings()
        QApplication.quit()

    def simulation_step(self):
        # Advance one tick of the running simulation.
        if self.simulation.is_running and not self.simulation.is_paused:
            finished_now = not self.simulation.step()

            # Update the wall BEFORE showing any dialog so the last climber is
            # visibly rendered at the summit instead of freezing at the level
            # just below it.
            self.update_ui()

            if finished_now and not self.simulation_finished:
                self.simulation_finished = True
                self.timer.stop()
                QMessageBox.information(
                    self, "Simulation finished",
                    "All climbers reached the top!\n\n"
                    "Press 'Stop' to end the simulation.")

    # ---- File menu ----

    def open_file(self):
        data = FileManager.open_file(self)
        if data is None:
            return
        self._load_from_data(data)

    def save_file(self):
        data = {
            "positions": list(self.simulation.progress),
            "climber_colors": [c.color.name() for c in self.simulation.climbers],
            "probability": self.simulation.probability,
            "speed": self.slider_speed.value(),
        }
        FileManager.save_file(data, self)

    def _load_from_data(self, data):
        if "positions" in data:
            self.simulation.set_progress(data["positions"])
            self.wall_widget.reset_animation()
        if "initial_heights" in data:
            self.simulation.set_initial_heights(data["initial_heights"])
            self.wall_widget.reset_animation()
        if "climber_colors" in data:
            self.climber_colors = list(data["climber_colors"])
            self.simulation.set_colors(self.climber_colors)
        if "probability" in data:
            prob = max(0, min(100, float(data["probability"])))
            self.slider_prob.setValue(int(prob))
            self.spin_prob.setText(str(int(prob)))
            self.simulation.probability = prob
        if "speed" in data:
            speed = max(0, min(100, int(data["speed"])))
            if speed == 0:
                speed = 30
            self.slider_speed.setValue(speed)
            self.spin_speed.setText(str(speed))
        self.update_ui()

    # ---- Settings menu ----

    def show_initial_fill_dialog(self):
        current_heights = list(self.simulation.initial_heights)
        dialog = InitialFillDialog(current_heights, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.simulation.set_initial_heights(dialog.get_values())
            self.wall_widget.reset_animation()
            self.update_ui()

    def open_color_picker(self):
        # Open the customization dialog; changes preview live on the climbers
        # and the final colors are applied when the dialog accepts.
        self.color_dialog = CustomizationDialog(
            self, current_colors=self.climber_colors)
        self.color_dialog.colors_changed.connect(self.on_colors_changed)
        self.color_dialog.colors_preview.connect(self.on_colors_changed)
        self.color_dialog.exec()

    def on_colors_changed(self, colors):
        self.climber_colors = list(colors)
        self.simulation.set_colors(self.climber_colors)
        self.update_ui()

    # ---- Help menu ----

    def show_about_program(self):
        QMessageBox.about(
            self, "About Program",
            "Climbing Simulation\n\n"
            "The installation has 10 climbers with unique colors. "
            "Each climbs a wall of 12 levels. The simulation runs until "
            "every climber has reached the top.\n\n"
            "Each tick a random climber climbs one level. With a given "
            "probability an alarm goes off and one of the climbers falls "
            "back a level. Climbers that have reached the top are removed "
            "from the run.\n\n"
            "Version 1.0")

    def show_about_author(self):
        QMessageBox.about(self, "About Author",
                          "Author: Teresenko Natalya, group 2302\n\n"
                          "Creator of the climbing simulation.")

    # ---- Speed / probability controls ----

    def update_speed(self):
        if (self.simulation.is_running and not self.simulation.is_paused
                and self.slider_speed.value() > 0):
            self.timer.start(1000 // self.slider_speed.value())
        elif self.slider_speed.value() == 0:
            self.timer.stop()

    def update_probability(self):
        self.simulation.probability = float(self.slider_prob.value())

    def update_speed_from_spin(self):
        value = self._spin_to_value(self.spin_speed, "Speed")
        if value is not None:
            self.slider_speed.setValue(value)

    def update_probability_from_spin(self):
        value = self._spin_to_value(self.spin_prob, "Probability")
        if value is not None:
            self.slider_prob.setValue(value)

    def _spin_to_value(self, line_edit, name):
        # Free-form numeric field: the value is rounded to the closest integer
        # (half rounds up) and the box is updated to show it. A warning dialog
        # pops up whenever the input can't be used exactly as typed.
        text = line_edit.text().strip()
        if not text:
            line_edit.setText("0")
            return 0

        reason = None
        if not all("0" <= char <= "9" for char in text):
            reason = "Invalid input, allowed symbols: 0-9."
            rounded = 0
        else:
            try:
                value = float(text)
            except (ValueError, OverflowError):
                reason = "Invalid input, allowed symbols: 0-9."
                rounded = 0
            else:
                if not math.isfinite(value):
                    rounded = 100
                    reason = (
                        "Invalid input, must be a number between 0 and 100. "
                        f"Rounded to {rounded}"
                    )
                else:
                    rounded = math.floor(value + 0.5)
                    if value < 0 or value > 100:
                        rounded = max(0, min(100, rounded))
                        reason = (
                            "Invalid input, must be a number between 0 and 100. "
                            f"Rounded to {rounded}"
                        )
                    elif rounded != value:
                        reason = f"{name}: {text} → {rounded}."

        if reason is not None:
            self._show_input_warning(reason)
        if text != str(rounded):
            line_edit.setText(str(rounded))
        return rounded

    def _show_input_warning(self, message):
        # Prompt a warning dialog explaining the input was adjusted; it closes
        # automatically after ~0.5s so it never blocks the user.
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Invalid input")
        msg.setText(message)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setModal(True)
        QTimer.singleShot(500, msg.accept)
        msg.exec()

        # ---- UI construction ----

    def setup_ui(self):
        self.setWindowTitle("Lab 1 - Climbing Simulation")
        self.setMinimumSize(900, 700)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Climber visualization area: all 10 climbers share one wall
        climber_group = QGroupBox("Climbers - Shared Wall")
        climber_layout = QVBoxLayout(climber_group)
        climber_layout.setContentsMargins(8, 8, 8, 8)

        self.wall_widget = ClimberWallWidget()
        climber_layout.addWidget(self.wall_widget)

        main_layout.addWidget(climber_group, 1)

        # Control bar
        control_group = QGroupBox("Simulation Control")
        control_layout = QHBoxLayout(control_group)

        speed_label = QLabel("Speed (ticks/sec):")
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(0, 100)
        self.slider_speed.setValue(30)
        self.spin_speed = QLineEdit("30")
        self.spin_speed.setFixedWidth(60)

        control_layout.addWidget(speed_label)
        control_layout.addWidget(self.slider_speed)
        control_layout.addWidget(self.spin_speed)

        prob_label = QLabel("Alarm probability (%):")
        self.slider_prob = QSlider(Qt.Orientation.Horizontal)
        self.slider_prob.setRange(0, 100)
        self.slider_prob.setValue(50)
        self.spin_prob = QLineEdit("50")
        self.spin_prob.setFixedWidth(60)

        control_layout.addWidget(prob_label)
        control_layout.addWidget(self.slider_prob)
        control_layout.addWidget(self.spin_prob)

        control_layout.addStretch()

        self.btn_start_stop = QPushButton("Start")
        self.btn_pause_continue = QPushButton("Pause")
        exit_button = QPushButton("Exit")

        control_layout.addWidget(self.btn_start_stop)
        control_layout.addWidget(self.btn_pause_continue)
        control_layout.addWidget(exit_button)

        main_layout.addWidget(control_group)

        self.statusBar().showMessage("Ready")

        # Connections
        self.btn_start_stop.clicked.connect(self.start_stop_simulation)
        self.btn_pause_continue.clicked.connect(self.pause_continue_simulation)
        exit_button.clicked.connect(self.exit_application)

        self.slider_speed.valueChanged.connect(self.update_speed)
        self.slider_prob.valueChanged.connect(self.update_probability)

        # Keep the sliders and the spin fields in sync in both directions.
        self.slider_speed.valueChanged.connect(
            lambda v: self.spin_speed.setText(str(v)))
        self.slider_prob.valueChanged.connect(
            lambda v: self.spin_prob.setText(str(v)))

        # Debounced validation: wait ~0.5s after the last keystroke before
        # checking/rounding the spin fields, instead of checking on Enter.
        self.spin_speed_timer = QTimer(self)
        self.spin_speed_timer.setSingleShot(True)
        self.spin_speed_timer.timeout.connect(self.update_speed_from_spin)
        self.spin_speed.textChanged.connect(
            lambda: self.spin_speed_timer.start(500))

        self.spin_prob_timer = QTimer(self)
        self.spin_prob_timer.setSingleShot(True)
        self.spin_prob_timer.timeout.connect(self.update_probability_from_spin)
        self.spin_prob.textChanged.connect(
            lambda: self.spin_prob_timer.start(500))

    def setup_menus(self):
        file_menu = self.menuBar().addMenu("File")
        self.save_action = file_menu.addAction("Save...")
        self.open_action = file_menu.addAction("Open...")
        file_menu.addSeparator()
        exit_action = file_menu.addAction("Exit")

        self.save_action.triggered.connect(self.save_file)
        self.open_action.triggered.connect(self.open_file)
        exit_action.triggered.connect(self.exit_application)

        settings_menu = self.menuBar().addMenu("Settings")
        self.color_action = settings_menu.addAction("Colors...")

        self.color_action.triggered.connect(self.open_color_picker)

        help_menu = self.menuBar().addMenu("Help")
        about_program = help_menu.addAction("About Program")
        about_author = help_menu.addAction("About Author")

        about_program.triggered.connect(self.show_about_program)
        about_author.triggered.connect(self.show_about_author)

    def update_ui(self):
        self.simulation.sync_heights()

        self.wall_widget.set_climbers(self.simulation.climbers)

        status = (f"Active: {len(self.simulation.active)}, "
                  f"Finished: {len(self.simulation.finish_order)}")
        if self.simulation.last_event:
            status += f" | {self.simulation.last_event}"
        if self.simulation.is_finished():
            status += " - Finished"
        self.statusBar().showMessage(status)

    # ---- Settings persistence ----

    def _config_file(self):
        config_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppConfigLocation)
        QDir().mkpath(config_dir)
        return os.path.join(config_dir, "settings.json")

    def load_settings(self):
        config_file = self._config_file()
        if not os.path.exists(config_file):
            return
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                self._load_from_data(json.load(f))
        except Exception:
            pass

    def save_settings(self):
        data = {
            "initial_heights": list(self.simulation.initial_heights),
            "climber_colors": [c.color.name() for c in self.simulation.climbers],
            "probability": self.simulation.probability,
            "speed": self.slider_speed.value(),
        }
        try:
            with open(self._config_file(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass