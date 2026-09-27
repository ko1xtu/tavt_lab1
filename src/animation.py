# Climber simulation model and the shared wall used to render it.
#
# Model: NUM_CLIMBERS climbers climb a wall of WALL_HEIGHT levels. Each tick
# one random active climber advances one level. With `probability` percent an
# "alarm" makes a random vulnerable climber (progress > 0) fall back one level.
# Reaching WALL_HEIGHT marks a climber as finished. The array O (initial
# heights) is kept so a run can be restarted from the user-chosen starting
# distribution.
#
# Rendering: all climbers share ONE screen. A single ClimberWallWidget draws
# every climber on the same wall, each in its own lane, so the whole race is
# visible at once instead of one window/card per person.

import os
import random
from PyQt6.QtCore import Qt, QPointF, QRectF, QEasingCurve, QTimer, QVariantAnimation
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPalette
from PyQt6.QtWidgets import QWidget

NUM_CLIMBERS = 10
WALL_HEIGHT = 12
WALL_TILES = 6          # vertical bg tiles: 5 rock tiles + 1 summit cap (bg_top)
FINISH_OFFSET_PX = 4    # how far finished climbers sink below the summit-tile center
FLAG_OFFSET_PX = 14     # flag sits this far right of the finished climber's lane center
CLIMB_FLIP_INTERVAL_MS = 140  # stride flips per leg during a climb (rapid)

# Folder holding the pixel-art sprites (next to the src/ package).
SPRITE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "sprites"))

DEFAULT_PALETTE = [
    "#E63946", "#F4A261", "#E9C46A", "#2A9D8F", "#264653",
    "#A8DADC", "#457B9D", "#1D3557", "#9B5DE5", "#F15BB5"
]


class Climber:
    # One climber: how far up the wall they are and their color.
    def __init__(self, color=QColor(Qt.GlobalColor.gray)):
        self.height = 0
        self.color = QColor(color)

    def copy_from(self, other):
        self.height = other.height
        self.color = QColor(other.color)
        return self


class Simulation:
    # Holds the climber state and advances the simulation one tick at a time.
    def __init__(self):
        self.climbers = [Climber(c) for c in DEFAULT_PALETTE]

        self.initial_heights = [0] * NUM_CLIMBERS
        self.progress = [0] * NUM_CLIMBERS       # levels reached by each climber
        self.finished = [False] * NUM_CLIMBERS   # True once a climber is at the top
        self.active = set(range(NUM_CLIMBERS))   # climbers still climbing
        self.finish_order = []                   # climbers in order they arrived

        self.probability = 50.0                  # alarm probability in percent
        self.is_running = False
        self.is_paused = False
        self.last_event = ""

        self.set_initial_heights([0] * NUM_CLIMBERS)

    def set_colors(self, colors):
        for i, color in enumerate(colors):
            if i < NUM_CLIMBERS:
                self.climbers[i].color = QColor(color)

    def set_initial_heights(self, heights):
        # (Re)build the starting distribution and reset the run. Initial heights
        # are clamped below the wall top so every climber starts climbing.
        self.initial_heights = []
        for i in range(NUM_CLIMBERS):
            h = heights[i] if i < len(heights) else 0
            self.initial_heights.append(max(0, min(WALL_HEIGHT - 1, int(h))))
        self.reset()

    def reset(self):
        # Fresh run: everybody starts from their initial heights.
        self.progress = list(self.initial_heights)
        self.finished = [p >= WALL_HEIGHT for p in self.progress]
        self.active = {i for i, p in enumerate(self.progress) if p < WALL_HEIGHT}
        self.finish_order = [i for i, p in enumerate(self.progress) if p >= WALL_HEIGHT]
        self.last_event = ""

    def set_progress(self, heights):
        # Restore a saved mid-run state directly from the saved positions.
        self.progress = []
        for i in range(NUM_CLIMBERS):
            h = heights[i] if i < len(heights) else 0
            self.progress.append(max(0, min(WALL_HEIGHT, int(h))))
        self.finished = [p >= WALL_HEIGHT for p in self.progress]
        self.active = {i for i, p in enumerate(self.progress) if p < WALL_HEIGHT}
        self.finish_order = [i for i, p in enumerate(self.progress) if p >= WALL_HEIGHT]
        self.last_event = ""

    def step(self):
        # Advance one tick: return False when every climber has finished.
        if not self.active:
            return False

        # One random active climber climbs a level
        climber_id = random.choice(list(self.active))
        self.progress[climber_id] += 1

        if self.progress[climber_id] >= WALL_HEIGHT:
            # Reached the top: mark as finished and deactivate
            self.active.remove(climber_id)
            self.finished[climber_id] = True
            self.finish_order.append(climber_id)
            self.last_event = f"Climber {climber_id + 1} reached the top"
            return bool(self.active)

        # Alarm: with `probability`, a climbing climber with progress falls back
        if random.random() < self.probability / 100.0:
            vulnerable = [c for c in self.active if self.progress[c] > 0]
            if vulnerable:
                victim = random.choice(vulnerable)
                self.progress[victim] -= 1
                self.last_event = f"Alarm! Climber {victim + 1} fell back"
                return bool(self.active)

        self.last_event = f"Climber {climber_id + 1} climbed"
        return bool(self.active)

    def sync_heights(self):
        # Push the progress array into the Climber objects for the widgets.
        for i, climber in enumerate(self.climbers):
            climber.height = self.progress[i]

    def is_finished(self):
        return not self.active


class _Lane:
    # Animation state for a single climber's lane on the shared wall. Mirrors
    # the per-widget feedback of the old card view: bouncing height changes, a
    # scale pulse and a red alarm flash.
    def __init__(self, owner, index):
        self.owner = owner
        self.index = index
        # Private copy of the displayed climber; external mutations must not
        # disturb the previously shown value used for change detection.
        self.climber = Climber()
        self._last_height = 0
        self._animated_height = 0.0
        self._scale = 1.0
        self._alarm_intensity = 0.0
        self._alarm_active = False
        self._frame = 0
        self._mirror = False
        self._climbs = 0
        self._idle_pose = True

        # Height animation (bounce when it changes)
        self._height_anim = QVariantAnimation(owner)
        self._height_anim.setDuration(450)
        self._height_anim.setEasingCurve(QEasingCurve.Type.OutBounce)
        self._height_anim.valueChanged.connect(self._set_animated_height)

        # Scale bounce for visual feedback
        self._scale_anim = QVariantAnimation(owner)
        self._scale_anim.setDuration(250)
        self._scale_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._scale_anim.setStartValue(1.0)
        self._scale_anim.setKeyValueAt(0.5, 1.05)
        self._scale_anim.setEndValue(1.0)
        self._scale_anim.valueChanged.connect(self._set_scale)

        # Alarm flash (red pulse over one second)
        self._alarm_anim = QVariantAnimation(owner)
        self._alarm_anim.setDuration(1000)
        self._alarm_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._alarm_anim.setStartValue(0.0)
        self._alarm_anim.setKeyValueAt(0.5, 1.0)
        self._alarm_anim.setEndValue(0.0)
        self._alarm_anim.valueChanged.connect(self._set_alarm)
        self._alarm_anim.finished.connect(self._on_alarm_finished)

        # Rapid stride flips while the climber actively climbs a leg
        self._flip_timer = QTimer(owner)
        self._flip_timer.setInterval(CLIMB_FLIP_INTERVAL_MS)
        self._flip_timer.timeout.connect(self._on_flip_tick)

    # ---- Animation property slots ----

    def _set_animated_height(self, value):
        self._animated_height = float(value)
        self.owner.update()

    def _set_scale(self, value):
        self._scale = float(value)
        self.owner.update()

    def _set_alarm(self, value):
        self._alarm_intensity = float(value)
        self.owner.update()

    def _on_alarm_finished(self):
        self._alarm_active = False
        self._alarm_intensity = 0.0
        self.owner.update()

    def _on_flip_tick(self):
        self._mirror = not self._mirror
        self.owner.update()

    # ---- Public API ----

    def set_climber(self, climber):
        # Compare against the previously shown height and animate changes.
        new_height = climber.height
        height_changed = new_height != self._last_height
        decreased = new_height < self._last_height
        self._last_height = new_height

        self.climber.copy_from(climber)

        if height_changed:
            self._idle_pose = False
            if new_height >= WALL_HEIGHT:
                # f2 is reserved for the finish pose at the summit.
                self._flip_timer.stop()
                self._frame = 1
            elif decreased:
                # f3 is the falling/alarm pose.
                self._flip_timer.stop()
                self._frame = 2
            else:
                # f1 is the climbing pose; start with the next stride step
                # unmirrored... then let the rapid stride timer keep flipping.
                self._frame = 0
                self._climbs += 1
                self._mirror = (self._climbs % 2) == 0  # step1 unmirrored
                if not self._flip_timer.isActive():
                    self._flip_timer.start()
            self._height_anim.stop()
            self._height_anim.setStartValue(self._animated_height)
            self._height_anim.setEndValue(float(new_height))
            self._height_anim.start()

            self._scale_anim.stop()
            self._scale_anim.setStartValue(1.0)
            self._scale_anim.setKeyValueAt(0.5, 1.05)
            self._scale_anim.setEndValue(1.0)
            self._scale_anim.start()

            if decreased and not self._alarm_active:
                self._alarm_active = True
                self._alarm_anim.stop()
                self._alarm_anim.setStartValue(0.0)
                self._alarm_anim.setKeyValueAt(0.5, 1.0)
                self._alarm_anim.setEndValue(0.0)
                self._alarm_anim.start()
        elif (self._height_anim.state() == QVariantAnimation.State.Stopped
              and new_height < WALL_HEIGHT
              and not self._idle_pose):
            # Transitioned to rest: idle f1 pose with a random facing.
            self._flip_timer.stop()
            self._frame = 0
            self._mirror = random.random() < 0.5
            self._idle_pose = True

        self.owner.update()


class ClimberWallWidget(QWidget):
    # One shared screen for every climber: a single wall divided into lanes, so
    # nobody gets their own window and the whole race is visible at once.
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(720, 430)
        self.lanes = [_Lane(self, i) for i in range(NUM_CLIMBERS)]

        # Pixel-art sprites: the wall face tiles vertically (bg.png), the top
        # strip of the wall is the summit cap (bg_top.png), and climbers/flag
        # are drawn as small sprites anchored by their feet. Climber sprites
        # are stored grayscale-tinted: the art is converted to luminance and
        # recolored at runtime with each climber's palette color.
        self.bg = QPixmap(os.path.join(SPRITE_DIR, "bg.png"))
        self.bg_top = QPixmap(os.path.join(SPRITE_DIR, "bg_top.png"))
        self._climber_sources = [
            self._to_gray(QPixmap(os.path.join(SPRITE_DIR, "climber-f1.png"))),
            self._to_gray(QPixmap(os.path.join(SPRITE_DIR, "climber-f2.png"))),
            self._to_gray(QPixmap(os.path.join(SPRITE_DIR, "climber-f3.png"))),
        ]
        self.flag_sprite = self._to_gray(QPixmap(os.path.join(SPRITE_DIR, "flag.png")))
        # Pixels below the feet row inside each 25px climber frame.
        self._feet_offsets = [0, 0, 1]
        self._tint_cache = {}

    @staticmethod
    def _to_gray(pixmap):
        # Convert a sprite to a grayscale RGBA template: each pixel keeps its
        # alpha but its RGB is replaced by its luminance, ready to be tinted.
        img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        if img.isNull():
            return img
        for y in range(img.height()):
            for x in range(img.width()):
                c = img.pixelColor(x, y)
                alpha = c.alpha()
                if not alpha:
                    continue
                lum = int(0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue())
                c.setRgb(lum, lum, lum, alpha)
                img.setPixelColor(x, y, c)
        return img

    def _tinted(self, source, color, key_suffix):
        # Cached grayscale template recolored with the climber's palette color.
        key = (color.name(), key_suffix)
        pixmap = self._tint_cache.get(key)
        if pixmap is not None:
            return pixmap
        img = source.copy()
        cr, cg, cb = color.red(), color.green(), color.blue()
        for y in range(img.height()):
            for x in range(img.width()):
                c = img.pixelColor(x, y)
                alpha = c.alpha()
                if not alpha:
                    continue
                lum = c.red()  # grayscale template: RGB carries the luminance
                c.setRgb((cr * lum) // 255, (cg * lum) // 255, (cb * lum) // 255, alpha)
                img.setPixelColor(x, y, c)
        pixmap = QPixmap.fromImage(img)
        self._tint_cache[key] = pixmap
        return pixmap

    # ---- Public API ----

    def reset_animation(self):
        # Restart climb-step parity so a fresh run begins unmirrored (step1).
        for lane in self.lanes:
            lane._flip_timer.stop()
            lane._climbs = 0
            lane._mirror = False
            lane._idle_pose = True

    def set_climbers(self, climbers):
        for lane, climber in zip(self.lanes, climbers):
            lane.set_climber(climber)
        self.update()

    # ---- Drawing ----

    def _tile(self, painter, pixmap, left, top, right, bottom, tw, th):
        # Repeat a texture across a rectangle, each tile scaled up to (tw, th).
        if pixmap.isNull() or pixmap.width() <= 0 or pixmap.height() <= 0:
            return
        for y in range(int(top), int(bottom), int(th)):
            for x in range(int(left), int(right), int(tw)):
                painter.drawPixmap(x, y, int(tw), int(th), pixmap)

    def _draw_climber(self, painter, cx, feet_y, frame, frame_index, scale, mirror):
        # Pixel-art climber anchored by its feet, optionally scaled for the
        # bounce feedback; `mirror` flips the climbing pose horizontally.
        frame_w = frame.width()
        frame_h = frame.height()
        if frame_h <= 0 or frame_w <= 0:
            return
        painter.save()
        painter.translate(cx, feet_y)
        painter.scale(-scale if mirror else scale, scale)
        painter.drawPixmap(round(-frame_w / 2),
                           round(-(frame_h - self._feet_offsets[frame_index])),
                           frame)
        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Scale pixel art with nearest-neighbor so upscaling stays crisp.
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        w = self.width()
        h = self.height()

        is_dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        text_color = QColor("white") if is_dark else QColor("black")

        # Split the widget into columns (one per climber) and, vertically, the
        # WALL_TILES wall tiles plus one extra "row 0" ground band at the
        # bottom where climbers at height 0 stand. Every 64x64 sprite tile is
        # scaled up to fill its cell.
        tile_w = w / NUM_CLIMBERS
        tile_h = h / (WALL_TILES + 1)
        wall_left = 0.0
        wall_top = 0.0
        wall_w = float(w)
        wall_h = tile_h * WALL_TILES    # wall face; row 0 ground band sits below
        wall_right = wall_w
        wall_bottom = wall_h
        lane_w = tile_w

        # Sprites use the vertical tile scale so climbers stay aligned to wall
        # levels even when the window stretches the wall horizontally.
        scale = tile_h / 64.0

        # Wall texture: summit cap on top (last tile = bg_top), rock below, and
        # the same rock tiles fill the bottom row 0 ground band.
        cap = wall_top + tile_h
        self._tile(painter, self.bg_top, wall_left, wall_top, wall_right, cap, tile_w, tile_h)
        self._tile(painter, self.bg, wall_left, cap, wall_right, wall_bottom, tile_w, tile_h)
        self._tile(painter, self.bg, wall_left, wall_bottom, wall_right, float(h), tile_w, tile_h)

        # Lane separators
        sep = QColor("#000000" if not is_dark else "#ffffff")
        for i in range(1, NUM_CLIMBERS):
            x = wall_left + lane_w * i
            painter.setPen(QPen(QColor(sep.red(), sep.green(), sep.blue(), 40), 1))
            painter.drawLine(QPointF(x, wall_top + 2), QPointF(x, float(h)))

        # Climber lanes
        for i, lane in enumerate(self.lanes):
            cx = wall_left + lane_w * (i + 0.5)

            # Level positions: height 0 stands on the very bottom edge (the
            # row 0 ground band); the summit sits at the top of the widget.
            fraction = max(0.0, min(1.0, lane._animated_height / WALL_HEIGHT))
            feet_y = float(h) - fraction * float(h)

            # Finished climbers stand on the summit: just below the middle of the
            # last (bg_top) tile instead of floating past the top of the wall.
            if lane.climber.height >= WALL_HEIGHT:
                feet_y = wall_top + tile_h / 2 + FINISH_OFFSET_PX * scale

            # Pixel climber sitting at the climbed height (tinted with the
            # climber's palette color), scaled like the wall behind it
            self._draw_climber(painter, cx, feet_y,
                               self._tinted(self._climber_sources[lane._frame],
                                            lane.climber.color, lane._frame),
                               lane._frame, lane._scale * scale, lane._mirror)

            # Alarm flash: red frame around the victim's lane
            if lane._alarm_intensity > 0.0:
                ring = QPen(QColor(255, 0, 0, int(255 * lane._alarm_intensity)), 2)
                painter.setPen(ring)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(cx - lane_w * 0.35, wall_top + 2,
                                        lane_w * 0.7, wall_h - 4))

            # Flag once the summit is reached, lane number otherwise
            font = painter.font()
            font.setPixelSize(max(8, int(10 * scale)))
            font.setBold(True)
            painter.setFont(font)
            if lane.climber.height >= WALL_HEIGHT and not self.flag_sprite.isNull():
                flag = self._tinted(self.flag_sprite, lane.climber.color, "flag")
                # Planted on the finish tile next to the finished climber
                finish_y = wall_top + tile_h / 2 + FINISH_OFFSET_PX * scale
                painter.save()
                painter.translate(cx, finish_y)
                painter.scale(scale, scale)
                painter.drawPixmap(FLAG_OFFSET_PX, -flag.height(), flag)
                painter.restore()
            painter.setPen(text_color)
            painter.drawText(QRectF(cx - lane_w / 2, wall_bottom + 4, lane_w, 14),
                             Qt.AlignmentFlag.AlignCenter, str(i + 1))

        painter.end()