# Copyright (c) 2025 CalSci
# Licensed under the MIT License.
#
# Graphing engine optimized for ST7565 + MicroPython:
# - Compiled expression cache
# - Adaptive per-column sampling
# - Discontinuity-safe line joining
# - Partial cursor refresh (column + bottom page)

try:
    import framebuf  # type: ignore
except ImportError:
    from mocking import framebuf  # type: ignore

import gc
import math
import utime as time  # type:ignore

from data_modules.object_handler import (
    current_app,
    display,
    form,
    form_refresh,
    keypad_state_manager,
    keypad_state_manager_reset,
    nav,
    typer,
)

DEBUG_GRAPH = False

def _dprint(*args):
    if DEBUG_GRAPH:
        print(*args)


def _ticks_diff(now_ms, start_ms):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(now_ms, start_ms)
    return now_ms - start_ms


def _ticks_add(base_ms, delta_ms):
    if hasattr(time, "ticks_add"):
        return time.ticks_add(base_ms, delta_ms)
    return base_ms + delta_ms


# Display config
DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64
DISPLAY_PAGES = DISPLAY_HEIGHT // 8
PLOT_HEIGHT_WITH_CURSOR = 56
PLOT_PAGES = (PLOT_HEIGHT_WITH_CURSOR + 7) // 8
BOTTOM_PAGE_INDEX = DISPLAY_PAGES - 1

# Navigation / interaction config
ZOOM_IN_FACTOR = 0.9
ZOOM_OUT_FACTOR = 1.1
PAN_SHIFT_FACTOR = 0.09       #  set 
INPUT_POLL_MS = 0.5
INPUT_POLL_SEC = INPUT_POLL_MS / 1000.0
FAST_POLL_RESUME_DELAY_MS = 500

# Plot quality config
SAMPLES_PER_PX_MIN = 5
SAMPLES_PER_PX_MAX = 100
EVAL_ABS_CLAMP = 1e10

# Reused tiny buffers for partial column updates.
_CURSOR_COL_BUF_A = bytearray(PLOT_PAGES)
_CURSOR_COL_BUF_B = bytearray(PLOT_PAGES)

# Expression compile cache
_EVAL_CACHE_EXPR = None
_EVAL_CACHE_FN = None


EVAL_GLOBALS = {
    "__builtins__": {},
    # Functions
    "abs": abs,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "ceil": math.ceil,
    "copysign": math.copysign,
    "degrees": math.degrees,
    "exp": math.exp,
    "fabs": math.fabs,
    "floor": math.floor,
    "fmod": math.fmod,
    "frexp": math.frexp,
    "ldexp": math.ldexp,
    "log": math.log,
    "modf": math.modf,
    "pow": math.pow,
    "radians": math.radians,
    "sqrt": math.sqrt,
    "trunc": math.trunc,
    # Constants
    "pi": math.pi,
    "e": math.e,
}


class MediumDigits:
    """5x7 font for cursor coordinate text."""

    data = {
        " ": [0x00, 0x00, 0x00, 0x00, 0x00],
        "0": [0x3E, 0x51, 0x49, 0x45, 0x3E],
        "1": [0x00, 0x42, 0x7F, 0x40, 0x00],
        "2": [0x42, 0x61, 0x51, 0x49, 0x46],
        "3": [0x21, 0x41, 0x45, 0x4B, 0x31],
        "4": [0x18, 0x14, 0x12, 0x7F, 0x10],
        "5": [0x27, 0x45, 0x45, 0x45, 0x39],
        "6": [0x3C, 0x4A, 0x49, 0x49, 0x30],
        "7": [0x01, 0x71, 0x09, 0x05, 0x03],
        "8": [0x36, 0x49, 0x49, 0x49, 0x36],
        "9": [0x06, 0x49, 0x49, 0x29, 0x1E],
        ".": [0x00, 0x60, 0x60, 0x00, 0x00],
        "-": [0x08, 0x08, 0x08, 0x08, 0x08],
        "x": [0x44, 0x28, 0x10, 0x28, 0x44],
        "y": [0x0C, 0x50, 0x50, 0x50, 0x3C],
        "u": [0x3C, 0x40, 0x40, 0x20, 0x7C],
        "n": [0x7C, 0x08, 0x04, 0x04, 0x78],
        "d": [0x38, 0x54, 0x54, 0x54, 0x18],
        "e": [0x38, 0x54, 0x54, 0x54, 0x18],
        "f": [0x08, 0x7E, 0x09, 0x01, 0x02],
    }

    @classmethod
    def get_char(cls, char):
        return cls.data.get(char, cls.data[" "])


class CursorState:
    """Cursor state for interactive graph mode."""

    def __init__(self):
        self.active = False
        self.x_pixel = DISPLAY_WIDTH // 2
        self.prev_x_pixel = self.x_pixel

    def toggle(self):
        self.active = not self.active
        self.prev_x_pixel = self.x_pixel

    def move(self, direction):
        self.prev_x_pixel = self.x_pixel
        if direction == "left" and self.x_pixel > 0:
            self.x_pixel -= 1
            return True
        if direction == "right" and self.x_pixel < DISPLAY_WIDTH - 1:
            self.x_pixel += 1
            return True
        return False


TOOL_NONE = 0
TOOL_AREA = 1
TOOL_TANGENT = 2
TOOL_NORMAL = 3
TOOL_MENU_ITEMS = (TOOL_AREA, TOOL_TANGENT, TOOL_NORMAL)
TOOL_LABELS = {
    TOOL_AREA: "Area",
    TOOL_TANGENT: "Tangent",
    TOOL_NORMAL: "Normal",
}
TOOL_SHORT_LABELS = {
    TOOL_AREA: "A",
    TOOL_TANGENT: "T",
    TOOL_NORMAL: "N",
}


class ToolFeature:
    """Single graph feature instance with x-value locking."""

    def __init__(self, mode, instance_number):
        self.mode = mode
        self.instance_number = instance_number
        self.area_x_left = 0.0
        self.area_x_right = 0.0
        self.area_focus = "right"
        self.single_x = 0.0

    def focused_x_value(self):
        if self.mode == TOOL_AREA:
            return self.area_x_left if self.area_focus == "left" else self.area_x_right
        return self.single_x

    def area_interval(self):
        if self.area_x_left <= self.area_x_right:
            return self.area_x_left, self.area_x_right
        return self.area_x_right, self.area_x_left

    def _sync_cursor(self, cursor, bounds):
        cursor.prev_x_pixel = cursor.x_pixel
        cursor.x_pixel = _x_value_to_pixel(self.focused_x_value(), bounds, clamp=True)

    def sync_cursor(self, cursor, bounds):
        self._sync_cursor(cursor, bounds)

    def initialize_from_cursor(self, cursor, bounds):
        x_center = _x_pixel_to_value(cursor.x_pixel, bounds)
        if self.mode == TOOL_AREA:
            x_step = _x_step_for_one_pixel(bounds)
            if x_step <= 0:
                x_step = 1e-6
            self.area_x_left = x_center - (10 * x_step)
            self.area_x_right = x_center + (10 * x_step)
            self.area_focus = "right"
        else:
            self.single_x = x_center

        self._sync_cursor(cursor, bounds)
        return True

    def focus_left(self, cursor, bounds):
        if self.mode != TOOL_AREA:
            return False
        self.area_focus = "left"
        self._sync_cursor(cursor, bounds)
        return True

    def focus_right(self, cursor, bounds):
        if self.mode != TOOL_AREA:
            return False
        self.area_focus = "right"
        self._sync_cursor(cursor, bounds)
        return True

    def move_focus(self, delta_px, bounds, cursor):
        x_step = _x_step_for_one_pixel(bounds)
        if x_step == 0:
            return False
        delta_x = delta_px * x_step

        if self.mode == TOOL_AREA:
            if self.area_focus == "left":
                self.area_x_left += delta_x
            else:
                self.area_x_right += delta_x

            if self.area_x_left > self.area_x_right:
                self.area_x_left, self.area_x_right = self.area_x_right, self.area_x_left
                self.area_focus = "left" if self.area_focus == "right" else "right"
        else:
            self.single_x += delta_x

        self._sync_cursor(cursor, bounds)
        return True


class ToolState:
    """Collection of graph features with one selected feature for editing."""

    def __init__(self):
        self.features = []
        self.selected_index = None
        self._counters = {
            TOOL_AREA: 0,
            TOOL_TANGENT: 0,
            TOOL_NORMAL: 0,
        }

    @property
    def active(self):
        return len(self.features) > 0

    @property
    def mode(self):
        feature = self.selected_feature()
        if feature is None:
            return TOOL_NONE
        return feature.mode

    def selected_feature(self):
        if self.selected_index is None:
            return None
        if self.selected_index < 0 or self.selected_index >= len(self.features):
            return None
        return self.features[self.selected_index]

    def set_mode(self, mode, cursor, bounds):
        next_number = self._counters.get(mode, 0) + 1
        self._counters[mode] = next_number

        feature = ToolFeature(mode, next_number)
        feature.initialize_from_cursor(cursor, bounds)
        self.features.append(feature)
        self.selected_index = len(self.features) - 1
        feature.sync_cursor(cursor, bounds)
        return True

    def sync_cursor(self, cursor, bounds):
        feature = self.selected_feature()
        if feature is not None:
            feature.sync_cursor(cursor, bounds)

    def focus_left(self, cursor, bounds):
        feature = self.selected_feature()
        if feature is None:
            return False
        return feature.focus_left(cursor, bounds)

    def focus_right(self, cursor, bounds):
        feature = self.selected_feature()
        if feature is None:
            return False
        return feature.focus_right(cursor, bounds)

    def move_focus(self, delta_px, bounds, cursor):
        feature = self.selected_feature()
        if feature is None:
            return False
        return feature.move_focus(delta_px, bounds, cursor)

    def select_index(self, index):
        if index < 0 or index >= len(self.features):
            return False
        changed = self.selected_index != index
        self.selected_index = index
        return changed

    def remove_index(self, index):
        if index < 0 or index >= len(self.features):
            return False
        del self.features[index]

        if not self.features:
            self.selected_index = None
            return True

        if self.selected_index is None:
            self.selected_index = 0
            return True

        if self.selected_index > index:
            self.selected_index -= 1
        elif self.selected_index == index and self.selected_index >= len(self.features):
            self.selected_index = len(self.features) - 1
        return True

    def count_by_mode(self, mode):
        count = 0
        for feature in self.features:
            if feature.mode == mode:
                count += 1
        return count


def draw_medium_text(fb, text_value, x, y):
    for char in text_value:
        char_data = MediumDigits.get_char(char)
        for col in range(5):
            byte = char_data[col]
            for row in range(7):
                if byte & (1 << row):
                    fb.pixel(x + col, y + row, 1)
        x += 6


def format_number(value):
    pi_multiple = value / math.pi
    if abs(pi_multiple - round(pi_multiple)) < 0.001:
        multiple = int(round(pi_multiple))
        if multiple == 0:
            return "0 "
        if multiple == 1:
            return "pi "
        if multiple == -1:
            return "-pi "
        return str(multiple) + "*pi "

    abs_v = abs(value)
    if abs_v < 0.01:
        return "0 "
    if abs_v < 100:
        return str(round(value, 2)) + " "
    if abs_v < 100000:
        return str(int(value)) + " "
    return "{:.3g} ".format(value)


def _display_full(fb_buf):
    display.graphics(fb_buf, page=0, column=0, width=DISPLAY_WIDTH, pages=DISPLAY_PAGES)


def _display_page(fb_buf, page_index):
    start = page_index * DISPLAY_WIDTH
    end = start + DISPLAY_WIDTH
    display.graphics(memoryview(fb_buf)[start:end], page=page_index, column=0, width=DISPLAY_WIDTH, pages=1)


def _display_plot_column(fb_buf, x_pixel, out_col_buf):
    if x_pixel < 0 or x_pixel >= DISPLAY_WIDTH:
        return
    idx = x_pixel
    for page in range(PLOT_PAGES):
        out_col_buf[page] = fb_buf[idx]
        idx += DISPLAY_WIDTH
    display.graphics(out_col_buf, page=0, column=x_pixel, width=1, pages=PLOT_PAGES)


def _samples_per_px_for_view(x_range):
    """Adaptive sampling by world-units per pixel (zoom-aware quality control)."""
    if DISPLAY_WIDTH < 2:
        return 1

    units_per_px = abs(x_range) / (DISPLAY_WIDTH - 1)
    if units_per_px <= 0.03:
        return 6
    if units_per_px <= 0.08:
        return 5
    if units_per_px <= 0.20:
        return 4
    if units_per_px <= 0.60:
        return 3
    if units_per_px <= 1.5:
        return 2
    return 1


def _make_eval_fn(expression):
    try:
        compiled = compile(expression, "<graph_expr>", "eval")
    except Exception:
        return None

    env = EVAL_GLOBALS

    def _eval_x(x_value):
        env["x"] = x_value
        return eval(compiled, env)

    return _eval_x


def get_eval_fn(expression):
    global _EVAL_CACHE_EXPR, _EVAL_CACHE_FN
    if expression != _EVAL_CACHE_EXPR:
        _EVAL_CACHE_EXPR = expression
        _EVAL_CACHE_FN = _make_eval_fn(expression)
    return _EVAL_CACHE_FN


def safe_eval(eval_fn, x_value):
    try:
        y_value = eval_fn(x_value)
        if y_value != y_value:
            return None
        if y_value > EVAL_ABS_CLAMP or y_value < -EVAL_ABS_CLAMP:
            return None
        return y_value
    except Exception:
        return None


def get_bounds():
    return {
        "x_min": eval(form.inp_list()["inp_1"], EVAL_GLOBALS),
        "x_max": eval(form.inp_list()["inp_2"], EVAL_GLOBALS),
        "y_min": eval(form.inp_list()["inp_3"], EVAL_GLOBALS),
        "y_max": eval(form.inp_list()["inp_4"], EVAL_GLOBALS),
    }


def update_bounds(bounds):
    form.input_list["inp_1"] = format_number(bounds["x_min"])
    form.input_list["inp_2"] = format_number(bounds["x_max"])
    form.input_list["inp_3"] = format_number(bounds["y_min"])
    form.input_list["inp_4"] = format_number(bounds["y_max"])


def apply_zoom(bounds, factor):
    x_range = bounds["x_max"] - bounds["x_min"]
    y_range = bounds["y_max"] - bounds["y_min"]
    x_center = (bounds["x_min"] + bounds["x_max"]) * 0.5
    y_center = (bounds["y_min"] + bounds["y_max"]) * 0.5
    new_x_range = x_range * factor
    new_y_range = y_range * factor
    return {
        "x_min": x_center - (new_x_range * 0.5),
        "x_max": x_center + (new_x_range * 0.5),
        "y_min": y_center - (new_y_range * 0.5),
        "y_max": y_center + (new_y_range * 0.5),
    }


def apply_pan(bounds, direction):
    x_range = bounds["x_max"] - bounds["x_min"]
    y_range = bounds["y_max"] - bounds["y_min"]
    out = bounds.copy()
    if direction == "up":
        delta = y_range * PAN_SHIFT_FACTOR
        out["y_min"] += delta
        out["y_max"] += delta
    elif direction == "down":
        delta = y_range * PAN_SHIFT_FACTOR
        out["y_min"] -= delta
        out["y_max"] -= delta
    elif direction == "left":
        delta = x_range * PAN_SHIFT_FACTOR
        out["x_min"] -= delta
        out["x_max"] -= delta
    elif direction == "right":
        delta = x_range * PAN_SHIFT_FACTOR
        out["x_min"] += delta
        out["x_max"] += delta
    return out


def _draw_axes(fb, x_min, x_max, y_min, y_max, x_scale, y_scale, plot_height):
    x_axis_y = -1
    y_axis_x = -1

    if y_min <= 0 <= y_max:
        x_axis_y = int((y_max / y_scale) + 0.5)
    if x_min <= 0 <= x_max:
        y_axis_x = int((0 - x_min) / x_scale + 0.5)

    if 0 <= x_axis_y < plot_height:
        fb.hline(0, x_axis_y, DISPLAY_WIDTH, 1)
    if 0 <= y_axis_x < DISPLAY_WIDTH:
        fb.vline(y_axis_x, 0, plot_height, 1)


def plot_function(fb, eval_fn, bounds, plot_height):
    x_min = bounds["x_min"]
    x_max = bounds["x_max"]
    y_min = bounds["y_min"]
    y_max = bounds["y_max"]

    if DISPLAY_WIDTH < 2 or plot_height < 2:
        return False

    x_range = x_max - x_min
    y_range = y_max - y_min
    if x_range == 0 or y_range == 0:
        return False

    x_scale = x_range / (DISPLAY_WIDTH - 1)
    y_scale = y_range / (plot_height - 1)
    inv_y_scale = 1.0 / y_scale

    _draw_axes(fb, x_min, x_max, y_min, y_max, x_scale, y_scale, plot_height)

    spp = _samples_per_px_for_view(x_range)
    if spp < SAMPLES_PER_PX_MIN:
        spp = SAMPLES_PER_PX_MIN
    if spp > SAMPLES_PER_PX_MAX:
        spp = SAMPLES_PER_PX_MAX

    pixel = fb.pixel
    line = fb.line
    vline = fb.vline

    sample_step = x_scale / spp
    left_shift = x_scale * 0.5
    connect_limit = (plot_height * 3) // 5
    steep_span_limit = (plot_height * 3) // 4
    discontinuity_span_limit = (plot_height * 5) // 6
    center_idx = spp >> 1

    prev_valid = False
    prev_steep = False
    prev_x = 0
    prev_y = 0

    for x_px in range(DISPLAY_WIDTH):
        x_center = x_min + (x_px * x_scale)
        x_left = x_center - left_shift

        col_min = plot_height
        col_max = -1
        rep_y = -1
        valid_count = 0

        for sample_idx in range(spp):
            x_val = x_left + ((sample_idx + 0.5) * sample_step)
            y_val = safe_eval(eval_fn, x_val)
            if y_val is None or y_val < y_min or y_val > y_max:
                continue

            y_px = int(((y_max - y_val) * inv_y_scale) + 0.5)
            if y_px < 0 or y_px >= plot_height:
                continue

            valid_count += 1
            if y_px < col_min:
                col_min = y_px
            if y_px > col_max:
                col_max = y_px
            if sample_idx == center_idx:
                rep_y = y_px

        if col_max < 0:
            prev_valid = False
            prev_steep = False
            continue

        if rep_y < 0:
            rep_y = (col_min + col_max) >> 1

        col_span = col_max - col_min
        # Very tall column with sparse valid samples is typically an asymptote crossing.
        # Draw only representative point and break line continuity.
        if col_span >= discontinuity_span_limit and valid_count <= (spp - 1):
            pixel(x_px, rep_y, 1)
            prev_valid = False
            prev_steep = True
            prev_x = x_px
            prev_y = rep_y
            continue

        if col_min == col_max:
            pixel(x_px, col_min, 1)
        else:
            vline(x_px, col_min, (col_max - col_min + 1), 1)

        is_steep = col_span > steep_span_limit

        if prev_valid and (not prev_steep) and (not is_steep):
            if abs(rep_y - prev_y) <= connect_limit:
                line(prev_x, prev_y, x_px, rep_y, 1)

        prev_valid = True
        prev_steep = is_steep
        prev_x = x_px
        prev_y = rep_y

    return True


def _fmt_cursor_coord(value, prefix):
    if abs(value) < 0.01:
        text_value = prefix + " 0"
    elif abs(value) < 10:
        text_value = prefix + str(round(value, 2))
    else:
        text_value = prefix + str(int(value))
    return text_value[:8]


def _x_pixel_to_value(x_pixel, bounds):
    x_range = bounds["x_max"] - bounds["x_min"]
    if DISPLAY_WIDTH < 2:
        return bounds["x_min"]
    return bounds["x_min"] + (x_pixel / (DISPLAY_WIDTH - 1)) * x_range


def _x_step_for_one_pixel(bounds):
    if DISPLAY_WIDTH < 2:
        return 0.0
    return (bounds["x_max"] - bounds["x_min"]) / (DISPLAY_WIDTH - 1)


def _x_value_to_pixel(x_value, bounds, clamp=False):
    x_range = bounds["x_max"] - bounds["x_min"]
    if DISPLAY_WIDTH < 2 or x_range == 0:
        return 0 if clamp else None

    x_pos = ((x_value - bounds["x_min"]) / x_range) * (DISPLAY_WIDTH - 1)
    x_px = int(x_pos + 0.5)

    if clamp:
        if x_px < 0:
            return 0
        if x_px >= DISPLAY_WIDTH:
            return DISPLAY_WIDTH - 1
        return x_px

    if x_px < 0 or x_px >= DISPLAY_WIDTH:
        return None
    return x_px


def _y_value_to_pixel(y_value, bounds, plot_height):
    y_range = bounds["y_max"] - bounds["y_min"]
    if y_range == 0 or plot_height < 2:
        return None
    if y_value < bounds["y_min"] or y_value > bounds["y_max"]:
        return None
    y_px = int(((bounds["y_max"] - y_value) / y_range) * (plot_height - 1) + 0.5)
    if y_px < 0 or y_px >= plot_height:
        return None
    return y_px


def _compute_area_value(eval_fn, tool_feature):
    x0, x1 = tool_feature.area_interval()
    if x1 == x0:
        return 0.0

    span = x1 - x0
    samples = int(abs(span) * 32)
    if samples < 64:
        samples = 64
    elif samples > 2048:
        samples = 2048

    step = span / samples
    x = x0
    y_prev = safe_eval(eval_fn, x)
    if y_prev is None:
        return None

    area = 0.0
    for _ in range(samples):
        x += step
        y_now = safe_eval(eval_fn, x)
        if y_now is None:
            return None
        area += (y_prev + y_now) * 0.5 * step
        y_prev = y_now

    return area


def _draw_area_shade(fb, eval_fn, bounds, tool_feature, plot_height):
    x_left_val, x_right_val = tool_feature.area_interval()
    if x_right_val < bounds["x_min"] or x_left_val > bounds["x_max"]:
        return

    y_min = bounds["y_min"]
    y_max = bounds["y_max"]
    if y_min > 0 or y_max < 0:
        return

    y_range = y_max - y_min
    if y_range == 0:
        return

    y_scale = y_range / (plot_height - 1)
    axis_y = int((y_max / y_scale) + 0.5)
    if axis_y < 0 or axis_y >= plot_height:
        return

    draw_left_val = x_left_val if x_left_val > bounds["x_min"] else bounds["x_min"]
    draw_right_val = x_right_val if x_right_val < bounds["x_max"] else bounds["x_max"]
    x_left_px = _x_value_to_pixel(draw_left_val, bounds, clamp=True)
    x_right_px = _x_value_to_pixel(draw_right_val, bounds, clamp=True)
    if x_right_px < x_left_px:
        return

    for x_px in range(x_left_px, x_right_px + 1):
        if (x_px - x_left_px) & 1:
            continue

        x_val = _x_pixel_to_value(x_px, bounds)
        y_val = safe_eval(eval_fn, x_val)
        if y_val is None or y_val < y_min or y_val > y_max:
            continue

        y_px = int(((y_max - y_val) / y_scale) + 0.5)
        if y_px < 0 or y_px >= plot_height:
            continue

        top = axis_y if axis_y < y_px else y_px
        h = y_px - axis_y if y_px > axis_y else axis_y - y_px
        fb.vline(x_px, top, h + 1, 1)

    # Draw interval edges for easier identification when multiple areas are active.
    fb.vline(x_left_px, 0, plot_height, 1)
    if x_right_px != x_left_px:
        fb.vline(x_right_px, 0, plot_height, 1)


def _estimate_derivative(eval_fn, x_value, bounds):
    x_step = _x_step_for_one_pixel(bounds)
    if x_step == 0:
        return None
    h = abs(x_step) * 0.5
    if h < 1e-6:
        h = 1e-6

    y_prev = safe_eval(eval_fn, x_value - h)
    y_next = safe_eval(eval_fn, x_value + h)
    if y_prev is None or y_next is None:
        return None
    return (y_next - y_prev) / (2.0 * h)


def _draw_linear_feature(fb, bounds, plot_height, x0, y0, slope):
    x_min = bounds["x_min"]
    x_max = bounds["x_max"]
    y_min = bounds["y_min"]
    y_max = bounds["y_max"]
    x_range = x_max - x_min
    y_range = y_max - y_min
    if x_range == 0 or y_range == 0 or DISPLAY_WIDTH < 2:
        return

    prev_valid = False
    prev_x = 0
    prev_y = 0
    for x_px in range(DISPLAY_WIDTH):
        x_val = _x_pixel_to_value(x_px, bounds)
        y_val = y0 + (slope * (x_val - x0))
        if y_val < y_min or y_val > y_max:
            prev_valid = False
            continue

        y_px = _y_value_to_pixel(y_val, bounds, plot_height)
        if y_px is None:
            prev_valid = False
            continue

        fb.pixel(x_px, y_px, 1)
        if prev_valid:
            fb.line(prev_x, prev_y, x_px, y_px, 1)
        prev_valid = True
        prev_x = x_px
        prev_y = y_px


def _get_tangent_info(eval_fn, bounds, x_value):
    y_value = safe_eval(eval_fn, x_value)
    if y_value is None:
        return None, None
    slope = _estimate_derivative(eval_fn, x_value, bounds)
    return y_value, slope


def _draw_tangent_or_normal(fb, eval_fn, bounds, tool_feature, plot_height):
    x_value = tool_feature.single_x
    y_value, tan_slope = _get_tangent_info(eval_fn, bounds, x_value)
    if y_value is None or tan_slope is None:
        return

    if tool_feature.mode == TOOL_TANGENT:
        _draw_linear_feature(fb, bounds, plot_height, x_value, y_value, tan_slope)
    elif tool_feature.mode == TOOL_NORMAL:
        if abs(tan_slope) < 1e-9:
            x_px = _x_value_to_pixel(x_value, bounds, clamp=False)
            if x_px is not None:
                fb.vline(x_px, 0, plot_height, 1)
        else:
            _draw_linear_feature(fb, bounds, plot_height, x_value, y_value, -1.0 / tan_slope)

    x_px = _x_value_to_pixel(x_value, bounds, clamp=False)
    y_px = _y_value_to_pixel(y_value, bounds, plot_height)
    if x_px is None or y_px is None:
        return

    marker_x = x_px - 1 if x_px > 0 else 0
    marker_w = 3
    if marker_x + marker_w > DISPLAY_WIDTH:
        marker_w = DISPLAY_WIDTH - marker_x
    fb.hline(marker_x, y_px, marker_w, 1)

    marker_y = y_px - 1 if y_px > 0 else 0
    marker_h = 3
    if marker_y + marker_h > plot_height:
        marker_h = plot_height - marker_y
    fb.vline(x_px, marker_y, marker_h, 1)


def _format_value_short(value):
    abs_v = abs(value)
    if abs_v < 10:
        return str(round(value, 3))
    if abs_v < 1000:
        return str(round(value, 2))
    return "{:.3g}".format(value)


def _format_area_text(area_value):
    if area_value is None:
        return "A=undef"
    a = abs(area_value)
    if a < 1000:
        return "A=" + str(round(area_value, 4))
    return "A={:.4g}".format(area_value)


def _format_line_tool_text(tool_feature, x_value, y_value, tan_slope):
    x_text = _format_value_short(x_value)
    if y_value is None:
        return "x=" + x_text + " y=undef"

    if tool_feature.mode == TOOL_TANGENT:
        if tan_slope is None:
            return "x=" + x_text + " m=undef"
        return "x=" + x_text + " m=" + _format_value_short(tan_slope)

    if tan_slope is None:
        return "x=" + x_text + " n=undef"
    if abs(tan_slope) < 1e-9:
        return "x=" + x_text + " n=inf"
    return "x=" + x_text + " n=" + _format_value_short(-1.0 / tan_slope)


def _tool_instance_label(tool_feature):
    return TOOL_SHORT_LABELS[tool_feature.mode] + str(tool_feature.instance_number)


def _tool_row_text(tool_feature, bounds):
    x_px = _x_value_to_pixel(tool_feature.focused_x_value(), bounds, clamp=True)
    row = _tool_instance_label(tool_feature)
    if tool_feature.mode == TOOL_AREA:
        side = "L" if tool_feature.area_focus == "left" else "R"
        row = row + " " + side
    row = row + " px" + str(x_px)
    return row


def _draw_toolbox_menu(fb, fb_buf, selected_mode, tool_state):
    fb.fill(0)
    fb.text("TOOLBOX", 38, 2, 1)

    y = 16
    for mode in TOOL_MENU_ITEMS:
        prefix = ">" if mode == selected_mode else " "
        marker = "*" if mode == tool_state.mode else " "
        count = tool_state.count_by_mode(mode)
        count_text = ""
        if count:
            count_text = "(" + str(count) + ")"
        fb.text((prefix + marker + " " + TOOL_LABELS[mode] + count_text)[:21], 4, y, 1)
        y += 14

    fb.text("OK=add", 4, 54, 1)
    fb.text(",=list", 64, 54, 1)
    _display_full(fb_buf)


def _open_toolbox_menu(fb, fb_buf, tool_state):
    if tool_state.mode in TOOL_MENU_ITEMS:
        selected_mode = tool_state.mode
    else:
        selected_mode = TOOL_AREA

    while True:
        _draw_toolbox_menu(fb, fb_buf, selected_mode, tool_state)
        key = typer.start_typing()

        if key == "nav_u":
            idx = TOOL_MENU_ITEMS.index(selected_mode)
            selected_mode = TOOL_MENU_ITEMS[(idx - 1) % len(TOOL_MENU_ITEMS)]
        elif key == "nav_d":
            idx = TOOL_MENU_ITEMS.index(selected_mode)
            selected_mode = TOOL_MENU_ITEMS[(idx + 1) % len(TOOL_MENU_ITEMS)]
        elif key in ("ok", "toolbox"):
            return selected_mode
        elif key == "back":
            return None
        elif key == "home":
            return "home"
        elif key in ("alpha", "beta"):
            keypad_state_manager(x=key)


def _draw_used_tools_menu(fb, fb_buf, tool_state, bounds, selected_index, scroll_index):
    fb.fill(0)
    fb.text("USED TOOLS", 28, 2, 1)

    total = len(tool_state.features)
    if total == 0:
        fb.text("No active tools", 20, 24, 1)
        fb.text("BACK=exit", 28, 54, 1)
        _display_full(fb_buf)
        return

    visible_rows = 3
    y = 14
    for row in range(visible_rows):
        idx = scroll_index + row
        if idx >= total:
            break
        tool_feature = tool_state.features[idx]
        prefix = ">" if idx == selected_index else " "
        marker = "*" if idx == tool_state.selected_index else " "
        line = prefix + marker + _tool_row_text(tool_feature, bounds)
        fb.text(line[:21], 0, y, 1)
        y += 13

    position_text = str(selected_index + 1) + "/" + str(total)
    fb.text(position_text[:5], 102, 2, 1)
    fb.text("OK=sel AC=del", 0, 54, 1)
    _display_full(fb_buf)


def _open_used_tools_menu(fb, fb_buf, tool_state, bounds):
    selected_index = tool_state.selected_index if tool_state.selected_index is not None else 0
    scroll_index = 0
    changed = False

    while True:
        total = len(tool_state.features)
        if total > 0:
            if selected_index < 0:
                selected_index = 0
            elif selected_index >= total:
                selected_index = total - 1

            if selected_index < scroll_index:
                scroll_index = selected_index
            elif selected_index >= scroll_index + 3:
                scroll_index = selected_index - 2
        else:
            selected_index = 0
            scroll_index = 0

        _draw_used_tools_menu(fb, fb_buf, tool_state, bounds, selected_index, scroll_index)
        key = typer.start_typing()

        if key == "nav_u" and total > 0:
            selected_index = (selected_index - 1) % total
        elif key == "nav_d" and total > 0:
            selected_index = (selected_index + 1) % total
        elif key in ("ok", "exe") and total > 0:
            if tool_state.select_index(selected_index):
                changed = True
            return changed
        elif key in ("AC", "nav_b", "-") and total > 0:
            tool_state.remove_index(selected_index)
            changed = True
        elif key in ("back", ",", "toolbox"):
            return changed
        elif key == "home":
            return "home"
        elif key in ("alpha", "beta"):
            keypad_state_manager(x=key)


def draw_cursor_overlay(fb, cursor, bounds, eval_fn, plot_height, tool_state=None):
    tool_active = tool_state is not None and tool_state.active
    if not cursor.active and not tool_active:
        return

    selected_tool = None
    if tool_active:
        selected_tool = tool_state.selected_feature()

    if selected_tool is not None and selected_tool.mode == TOOL_AREA:
        x_left_val, x_right_val = selected_tool.area_interval()
        x_left = _x_value_to_pixel(x_left_val, bounds, clamp=False)
        x_right = _x_value_to_pixel(x_right_val, bounds, clamp=False)
        if x_left is not None:
            fb.vline(x_left, 0, plot_height, 1)
        if x_right is not None and x_right != x_left:
            fb.vline(x_right, 0, plot_height, 1)
        focus_x = _x_value_to_pixel(selected_tool.focused_x_value(), bounds, clamp=False)
        if focus_x is not None and cursor.active:
            marker_x = focus_x - 1 if focus_x > 0 else 0
            marker_w = 3
            if marker_x + marker_w > DISPLAY_WIDTH:
                marker_w = DISPLAY_WIDTH - marker_x
            fb.hline(marker_x, 0, marker_w, 1)
        fb.fill_rect(0, plot_height, DISPLAY_WIDTH, DISPLAY_HEIGHT - plot_height, 0)
        area_value = _compute_area_value(eval_fn, selected_tool)
        focus_px = _x_value_to_pixel(selected_tool.focused_x_value(), bounds, clamp=True)
        info_text = _tool_instance_label(selected_tool) + " p" + str(focus_px)
        info_text = info_text + " " + _format_area_text(area_value)
        fb.text(info_text[:21], 0, plot_height, 1)
        return

    if selected_tool is not None and selected_tool.mode in (TOOL_TANGENT, TOOL_NORMAL):
        x_value = selected_tool.single_x
        x_px = _x_value_to_pixel(x_value, bounds, clamp=False)
        if x_px is not None:
            fb.vline(x_px, 0, plot_height, 1)
        y_value, tan_slope = _get_tangent_info(eval_fn, bounds, x_value)
        fb.fill_rect(0, plot_height, DISPLAY_WIDTH, DISPLAY_HEIGHT - plot_height, 0)
        focus_px = _x_value_to_pixel(x_value, bounds, clamp=True)
        info_text = _tool_instance_label(selected_tool) + " p" + str(focus_px)
        info_text = info_text + " " + _format_line_tool_text(selected_tool, x_value, y_value, tan_slope)
        fb.text(info_text[:21], 0, plot_height, 1)
        return

    x_range = bounds["x_max"] - bounds["x_min"]
    if x_range == 0 or DISPLAY_WIDTH < 2:
        return

    x_coord = bounds["x_min"] + (cursor.x_pixel / (DISPLAY_WIDTH - 1)) * x_range
    fb.vline(cursor.x_pixel, 0, plot_height, 1)

    draw_medium_text(fb, _fmt_cursor_coord(x_coord, "x"), 2, plot_height + 1)
    y_coord = safe_eval(eval_fn, x_coord)
    if y_coord is None:
        draw_medium_text(fb, "y undef", DISPLAY_WIDTH - 42, plot_height + 1)
    else:
        draw_medium_text(fb, _fmt_cursor_coord(y_coord, "y"), DISPLAY_WIDTH - 42, plot_height + 1)


def replot(fb, fb_buf, expression, bounds, cursor, cache_buf=None, tool_state=None):
    start_ms = time.ticks_ms()

    eval_fn = get_eval_fn(expression)
    if eval_fn is None:
        fb.fill(0)
        draw_medium_text(fb, "expr err", 2, 57)
        _display_full(fb_buf)
        return False

    fb.fill(0)
    tool_active = tool_state is not None and tool_state.active
    plot_height = DISPLAY_HEIGHT if not (cursor.active or tool_active) else PLOT_HEIGHT_WITH_CURSOR

    if not plot_function(fb, eval_fn, bounds, plot_height):
        draw_medium_text(fb, "range err", 2, 57)

    if tool_active:
        for tool_feature in tool_state.features:
            if tool_feature.mode == TOOL_AREA:
                _draw_area_shade(fb, eval_fn, bounds, tool_feature, PLOT_HEIGHT_WITH_CURSOR)
            elif tool_feature.mode in (TOOL_TANGENT, TOOL_NORMAL):
                _draw_tangent_or_normal(fb, eval_fn, bounds, tool_feature, PLOT_HEIGHT_WITH_CURSOR)

    if cache_buf is not None:
        cache_buf[:] = fb_buf

    if cursor.active or tool_active:
        draw_cursor_overlay(fb, cursor, bounds, eval_fn, PLOT_HEIGHT_WITH_CURSOR, tool_state)

    _display_full(fb_buf)
    _dprint("Replot:", _ticks_diff(time.ticks_ms(), start_ms), "ms")
    return True


def update_cursor_only(fb, fb_buf, cache_buf, cursor, bounds, expression, tool_state=None):
    start_ms = time.ticks_ms()
    eval_fn = get_eval_fn(expression)

    if tool_state is not None and tool_state.active:
        replot(fb, fb_buf, expression, bounds, cursor, cache_buf, tool_state)
        return

    fb_buf[:] = cache_buf

    if cursor.active and eval_fn is not None:
        draw_cursor_overlay(fb, cursor, bounds, eval_fn, PLOT_HEIGHT_WITH_CURSOR, tool_state)
        _display_plot_column(fb_buf, cursor.prev_x_pixel, _CURSOR_COL_BUF_A)
        if cursor.x_pixel != cursor.prev_x_pixel:
            _display_plot_column(fb_buf, cursor.x_pixel, _CURSOR_COL_BUF_B)
        _display_page(fb_buf, BOTTOM_PAGE_INDEX)
    else:
        _display_full(fb_buf)

    _dprint("Cursor update:", _ticks_diff(time.ticks_ms(), start_ms), "ms")


def _set_initial_form():
    form.input_list = {
        "inp_0": "x*sin(x) ",
        "inp_1": "-20 ",
        "inp_2": "20 ",
        "inp_3": "-10 ",
        "inp_4": "10 ",
    }
    form.form_list = [
        "enter function:f(x)",
        "inp_0",
        "enter x_min:",
        "inp_1",
        "enter x_max:",
        "inp_2",
        "enter y_min:",
        "inp_3",
        "enter y_max:",
        "inp_4",
    ]
    form.update()


def graph(db={}):
    _dprint("Graph start, mem:", gc.mem_free())
    keypad_state_manager_reset()

    prev_debounce = getattr(typer, "debounce_delay_time", None)

    def _set_fast_poll():
        if prev_debounce is not None:
            typer.debounce_delay_time = INPUT_POLL_SEC

    def _restore_default_poll():
        if prev_debounce is not None:
            typer.debounce_delay_time = prev_debounce

    try:
        _set_initial_form()
        form_refresh.refresh()

        fb_buf = bytearray((DISPLAY_WIDTH * DISPLAY_HEIGHT) // 8)
        fb = framebuf.FrameBuffer(fb_buf, DISPLAY_WIDTH, DISPLAY_HEIGHT, framebuf.MONO_VLSB)
        cache_buf = bytearray(len(fb_buf))
        cursor = CursorState()
        tool_state = ToolState()

        while True:
            _restore_default_poll()
            inp = typer.start_typing()

            if inp == "back":
                current_app[0] = "scientific_calculator"
                current_app[1] = "application_modules"
                break

            if inp == "home":
                current_app[0] = "home"
                current_app[1] = "root"
                return

            if inp == "ok":
                try:
                    bounds = get_bounds()
                except Exception as exc:
                    _dprint("Bounds parse error:", exc)
                    continue

                gc.collect()
                expression = form.inp_list()["inp_0"]
                replot(fb, fb_buf, expression, bounds, cursor, cache_buf, tool_state)
                fast_poll_block_until_ms = None

                try:
                    while True:
                        feature_active = cursor.active or tool_state.active
                        if feature_active:
                            _restore_default_poll()
                        else:
                            if (
                                fast_poll_block_until_ms is not None
                                and _ticks_diff(time.ticks_ms(), fast_poll_block_until_ms) < 0
                            ):
                                _restore_default_poll()
                            else:
                                _set_fast_poll()

                        key = typer.start_typing()

                        if key in ("a", "A", "module", "copy"):
                            cursor.toggle()
                            if cursor.active and tool_state.active:
                                tool_state.sync_cursor(cursor, bounds)
                            feature_active = cursor.active or tool_state.active
                            if feature_active:
                                _restore_default_poll()
                                fast_poll_block_until_ms = None
                            else:
                                _restore_default_poll()
                                fast_poll_block_until_ms = _ticks_add(
                                    time.ticks_ms(), FAST_POLL_RESUME_DELAY_MS
                                )
                            expression = form.inp_list()["inp_0"]
                            replot(fb, fb_buf, expression, bounds, cursor, cache_buf, tool_state)

                        elif key == "+":
                            bounds = apply_zoom(bounds, ZOOM_IN_FACTOR)
                            update_bounds(bounds)
                            if cursor.active and tool_state.active:
                                tool_state.sync_cursor(cursor, bounds)
                            expression = form.inp_list()["inp_0"]
                            replot(fb, fb_buf, expression, bounds, cursor, cache_buf, tool_state)

                        elif key == "-":
                            bounds = apply_zoom(bounds, ZOOM_OUT_FACTOR)
                            update_bounds(bounds)
                            if cursor.active and tool_state.active:
                                tool_state.sync_cursor(cursor, bounds)
                            expression = form.inp_list()["inp_0"]
                            replot(fb, fb_buf, expression, bounds, cursor, cache_buf, tool_state)

                        elif key == "nav_u":
                            handled = False
                            if cursor.active and tool_state.mode == TOOL_AREA:
                                handled = tool_state.focus_left(cursor, bounds)
                            if handled:
                                expression = form.inp_list()["inp_0"]
                                replot(fb, fb_buf, expression, bounds, cursor, cache_buf, tool_state)
                            else:
                                bounds = apply_pan(bounds, "up")
                                update_bounds(bounds)
                                if tool_state.active:
                                    tool_state.sync_cursor(cursor, bounds)
                                expression = form.inp_list()["inp_0"]
                                replot(fb, fb_buf, expression, bounds, cursor, cache_buf, tool_state)

                        elif key == "nav_d":
                            handled = False
                            if cursor.active and tool_state.mode == TOOL_AREA:
                                handled = tool_state.focus_right(cursor, bounds)
                            if handled:
                                expression = form.inp_list()["inp_0"]
                                replot(fb, fb_buf, expression, bounds, cursor, cache_buf, tool_state)
                            else:
                                bounds = apply_pan(bounds, "down")
                                update_bounds(bounds)
                                if tool_state.active:
                                    tool_state.sync_cursor(cursor, bounds)
                                expression = form.inp_list()["inp_0"]
                                replot(fb, fb_buf, expression, bounds, cursor, cache_buf, tool_state)

                        elif key == "nav_l":
                            if cursor.active:
                                if tool_state.active:
                                    moved = tool_state.move_focus(-1, bounds, cursor)
                                else:
                                    moved = cursor.move("left")
                                if moved:
                                    expression = form.inp_list()["inp_0"]
                                    update_cursor_only(fb, fb_buf, cache_buf, cursor, bounds, expression, tool_state)
                            else:
                                bounds = apply_pan(bounds, "left")
                                update_bounds(bounds)
                                if tool_state.active:
                                    tool_state.sync_cursor(cursor, bounds)
                                expression = form.inp_list()["inp_0"]
                                replot(fb, fb_buf, expression, bounds, cursor, cache_buf, tool_state)

                        elif key == "nav_r":
                            if cursor.active:
                                if tool_state.active:
                                    moved = tool_state.move_focus(1, bounds, cursor)
                                else:
                                    moved = cursor.move("right")
                                if moved:
                                    expression = form.inp_list()["inp_0"]
                                    update_cursor_only(fb, fb_buf, cache_buf, cursor, bounds, expression, tool_state)
                            else:
                                bounds = apply_pan(bounds, "right")
                                update_bounds(bounds)
                                if tool_state.active:
                                    tool_state.sync_cursor(cursor, bounds)
                                expression = form.inp_list()["inp_0"]
                                replot(fb, fb_buf, expression, bounds, cursor, cache_buf, tool_state)

                        elif key == "toolbox":
                            _restore_default_poll()
                            selected_mode = _open_toolbox_menu(fb, fb_buf, tool_state)
                            if selected_mode == "home":
                                current_app[0] = "home"
                                current_app[1] = "root"
                                return
                            if selected_mode is not None:
                                if not cursor.active:
                                    cursor.toggle()
                                tool_state.set_mode(selected_mode, cursor, bounds)
                            feature_active = cursor.active or tool_state.active
                            if feature_active:
                                _restore_default_poll()
                                fast_poll_block_until_ms = None
                            else:
                                _restore_default_poll()
                                fast_poll_block_until_ms = _ticks_add(
                                    time.ticks_ms(), FAST_POLL_RESUME_DELAY_MS
                                )
                            expression = form.inp_list()["inp_0"]
                            replot(fb, fb_buf, expression, bounds, cursor, cache_buf, tool_state)

                        elif key == ",":
                            _restore_default_poll()
                            menu_status = _open_used_tools_menu(fb, fb_buf, tool_state, bounds)
                            if menu_status == "home":
                                current_app[0] = "home"
                                current_app[1] = "root"
                                return
                            if cursor.active and tool_state.active:
                                tool_state.sync_cursor(cursor, bounds)
                            feature_active = cursor.active or tool_state.active
                            if feature_active:
                                _restore_default_poll()
                                fast_poll_block_until_ms = None
                            else:
                                _restore_default_poll()
                                fast_poll_block_until_ms = _ticks_add(
                                    time.ticks_ms(), FAST_POLL_RESUME_DELAY_MS
                                )
                            expression = form.inp_list()["inp_0"]
                            replot(fb, fb_buf, expression, bounds, cursor, cache_buf, tool_state)

                        elif key in ("alpha", "beta"):
                            keypad_state_manager(x=key)

                        elif key == "back":
                            break

                        elif key == "home":
                            current_app[0] = "home"
                            current_app[1] = "root"
                            return
                finally:
                    _restore_default_poll()

                fb.fill(0)
                form.refresh_rows = (0, form.actual_rows)
                display.clear_display()
                form_refresh.refresh()

            elif inp in ("alpha", "beta"):
                keypad_state_manager(x=inp)
                form.update_buffer("")

            elif inp == "toolbox":
                pass

            elif inp not in ("ok",):
                form.update_buffer(inp)

            form_refresh.refresh(state=nav.current_state())

    finally:
        if prev_debounce is not None:
            typer.debounce_delay_time = prev_debounce
        gc.collect()
        _dprint("Graph end, mem:", gc.mem_free())


def polynom1(exp, x):
    """Backward-compatible evaluator."""
    eval_fn = get_eval_fn(exp)
    if eval_fn is None:
        raise ValueError("Invalid expression")
    return eval_fn(x)
