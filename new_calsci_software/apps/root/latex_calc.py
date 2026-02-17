import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# apps/root/math_renderer.py
# Mathematical expression renderer for CalSci based on coordinate layout system
# Renders fractions, exponents, and roots on 128x64 monochrome display

from mocking import framebuf
from data_modules.object_handler import display, typer, keypad_state_manager_reset, current_app
from data_modules.characters import Characters
import gc

FONT_5X8 = Characters.Chr5X8_data
CHAR_WIDTH = 6  # 5 pixels + 1 space
CHAR_HEIGHT = 8
BASELINE = 6

# ===== NODE STRUCTURE =====
class MathNode:
    def __init__(self, type, content=None, children=None):
        self.type = type  # 'text', 'frac', 'exp', 'sqrt', 'nroot'
        self.content = content
        self.children = children or []
        # Layout properties (calculated by measure)
        self.width = 0
        self.height = 0
        self.baseline = 0
        self.x = 0  # Absolute position
        self.y = 0

# ===== PARSER =====
def parse_latex(expr):
    """Parse LaTeX string to MathNode tree"""
    nodes = []
    i = 0
    
    while i < len(expr):
        # Check for \frac - need to check for actual backslash
        if i < len(expr) and expr[i] == '\\' and i+5 <= len(expr) and expr[i:i+5] == '\\frac':
            i += 5
            if i < len(expr) and expr[i] == '{':
                i += 1
                num, i = extract_braced(expr, i)
                # After extract_braced, i points after the closing }
                # Check if next character is opening { for denominator
                if i < len(expr) and expr[i] == '{':
                    i += 1
                    den, i = extract_braced(expr, i)
                    nodes.append(MathNode('frac', children=[parse_latex(num), parse_latex(den)]))
                    continue
        
        # Check for \sqrt
        if i < len(expr) and expr[i] == '\\' and i+5 <= len(expr) and expr[i:i+5] == '\\sqrt':
            i += 5
            root_order = None
            if i < len(expr) and expr[i] == '[':
                i += 1
                order_str, i = extract_bracketed(expr, i)
                root_order = parse_latex(order_str)
            if i < len(expr) and expr[i] == '{':
                i += 1
                content, i = extract_braced(expr, i)
                if root_order:
                    nodes.append(MathNode('nroot', children=[root_order, parse_latex(content)]))
                else:
                    nodes.append(MathNode('sqrt', children=[parse_latex(content)]))
                continue
        
        # Check for ^
        if i < len(expr) and expr[i] == '^':
            i += 1
            if i < len(expr) and expr[i] == '{':
                i += 1
                exp_str, i = extract_braced(expr, i)
                nodes.append(MathNode('exp', children=[parse_latex(exp_str)]))
                continue
        
        # Regular text
        text_start = i
        while i < len(expr) and expr[i] not in '\\^':
            i += 1
        if i > text_start:
            nodes.append(MathNode('text', content=expr[text_start:i]))
    
    return nodes

def extract_braced(s, start):
    """Extract content between {}"""
    depth = 1
    i = start
    while i < len(s) and depth > 0:
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
        i += 1
    return s[start:i-1], i

def extract_bracketed(s, start):
    """Extract content between []"""
    depth = 1
    i = start
    while i < len(s) and depth > 0:
        if s[i] == '[':
            depth += 1
        elif s[i] == ']':
            depth -= 1
        i += 1
    return s[start:i-1], i

# ===== LAYOUT MEASUREMENT =====
def measure_node(node):
    """
    Calculate width, height, baseline for a node
    Based on handwritten design:
    - Text: simple character width
    - Fraction: max(num_width, den_width), heights stacked
    - Exponent: raised by HE
    - Sqrt: content + radical symbol width
    """
    if node.type == 'text':
        node.width = len(node.content) * CHAR_WIDTH
        node.height = CHAR_HEIGHT
        node.baseline = BASELINE
    
    elif node.type == 'frac':
        # Measure children
        numerator = node.children[0]
        denominator = node.children[1]
        
        measure_nodes(numerator)
        measure_nodes(denominator)
        
        # Calculate dimensions per design
        num_w = sum(n.width for n in numerator)
        den_w = sum(n.width for n in denominator)
        num_h = max((n.height for n in numerator), default=CHAR_HEIGHT)
        den_h = max((n.height for n in denominator), default=CHAR_HEIGHT)
        
        # WF = max(num_width, den_width)
        node.width = max(num_w, den_w) + 4  # padding
        
        # Height: numerator + space + line + space + denominator
        HT_SPACE = 2  # spacing above/below fraction line
        LINE_HEIGHT = 1
        node.height = num_h + HT_SPACE + LINE_HEIGHT + HT_SPACE + den_h
        
        # Baseline at fraction line
        node.baseline = num_h + HT_SPACE
    
    elif node.type == 'exp':
        # Measure exponent content
        measure_nodes(node.children[0])
        
        exp_w = sum(n.width for n in node.children[0])
        exp_h = max((n.height for n in node.children[0]), default=CHAR_HEIGHT)
        
        node.width = exp_w
        # HE = height of exponent raise
        HE = 4
        node.height = CHAR_HEIGHT + HE
        node.baseline = BASELINE
    
    elif node.type == 'sqrt':
        # Measure content
        measure_nodes(node.children[0])
        
        cont_w = sum(n.width for n in node.children[0])
        cont_h = max((n.height for n in node.children[0]), default=CHAR_HEIGHT)
        cont_baseline = max((n.baseline for n in node.children[0]), default=BASELINE)
        
        # WRT = content width + radical symbol
        RADICAL_WIDTH = 8
        node.width = cont_w + RADICAL_WIDTH
        # Height: content height + 1 pixel margin top + 1 pixel margin bottom + tick space
        node.height = cont_h + 1 + 1 + 2  # top margin + bottom margin + tick
        node.baseline = cont_baseline + 1 + 2  # baseline + bottom margin + tick
    
    elif node.type == 'nroot':
        # Measure root order and content
        measure_nodes(node.children[0])  # order (e.g., "3" in ³√)
        measure_nodes(node.children[1])  # content
        
        order_w = sum(n.width for n in node.children[0])
        cont_w = sum(n.width for n in node.children[1])
        cont_h = max((n.height for n in node.children[1]), default=CHAR_HEIGHT)
        cont_baseline = max((n.baseline for n in node.children[1]), default=BASELINE)
        
        RADICAL_WIDTH = 8
        node.width = cont_w + RADICAL_WIDTH + order_w // 2
        node.height = cont_h + 1 + 1 + 2  # top margin + bottom margin + tick
        node.baseline = cont_baseline + 1 + 2

def measure_nodes(nodes):
    """Measure all nodes in list"""
    for node in nodes:
        measure_node(node)

# ===== LAYOUT POSITIONING =====
def layout_node(node, x, y, baseline):
    """
    Calculate absolute x,y positions for rendering
    Ensures node's own baseline aligns to the requested baseline.
    """
    node.x = x
    # IMPORTANT: align this node so (node.y + node.baseline) == (y + baseline)
    node.y = y + baseline - node.baseline

    if node.type == 'text':
        # already baseline-aligned by the generic rule above
        return

    elif node.type == 'frac':
        numerator = node.children[0]
        denominator = node.children[1]

        num_w = sum(n.width for n in numerator)
        den_w = sum(n.width for n in denominator)

        num_baseline = max((n.baseline for n in numerator), default=BASELINE)
        den_baseline = max((n.baseline for n in denominator), default=BASELINE)

        # Fraction line position MUST match render_node()
        line_y = node.y + node.baseline

        GAP = 1  # << smaller gap; makes numerator closer to the bar

        # Center horizontally
        num_offset_x = (node.width - num_w) // 2
        den_offset_x = (node.width - den_w) // 2

        # Place numerator so its baseline sits GAP pixels above the line
        num_baseline_y = line_y - GAP - 1
        num_y = num_baseline_y - num_baseline
        layout_nodes(numerator, node.x + num_offset_x, num_y, num_baseline)

        # Place denominator so its TOP starts GAP pixels below the line (plus 1px line thickness)
        den_top_y = line_y + 1 + GAP
        layout_nodes(denominator, node.x + den_offset_x, den_top_y, den_baseline)

    elif node.type == 'exp':
        HE = 4
        exp_baseline = max((n.baseline for n in node.children[0]), default=BASELINE)
        # raise exponent block
        exp_y = (node.y - HE)
        layout_nodes(node.children[0], node.x, exp_y, exp_baseline)

    elif node.type == 'sqrt':
        RADICAL_WIDTH = 8
        cont_baseline = max((n.baseline for n in node.children[0]), default=BASELINE)
        layout_nodes(node.children[0], node.x + RADICAL_WIDTH, node.y, cont_baseline)

    elif node.type == 'nroot':
        order_baseline = max((n.baseline for n in node.children[0]), default=BASELINE)
        cont_baseline = max((n.baseline for n in node.children[1]), default=BASELINE)

        layout_nodes(node.children[0], node.x, node.y, order_baseline)

        RADICAL_WIDTH = 8
        order_w = sum(n.width for n in node.children[0])
        rad_x = node.x + order_w // 2 + 2

        # Keep content baseline-aligned within this nroot box
        layout_nodes(node.children[1], rad_x + RADICAL_WIDTH, node.y, cont_baseline)


def layout_nodes(nodes, x, y, baseline):
    """Layout all nodes in list, updating x position"""
    current_x = x
    for node in nodes:
        layout_node(node, current_x, y, baseline)
        current_x += node.width

# ===== RENDERING =====
def draw_char(fb, char, x, y):
    """Draw single character"""
    data = FONT_5X8.get(char, FONT_5X8['*'])
    for col in range(5):
        byte = data[col]
        for row in range(8):
            if byte & (1 << row):
                fb.pixel(x + col, y + row, 1)

def get_actual_top(nodes):
    """Recursively find the topmost rendered pixel across all nodes"""
    if not nodes:
        return float('inf')
    
    min_top = float('inf')
    for node in nodes:
        node_top = node.y
        
        if node.children:
            for child_list in node.children:
                child_top = get_actual_top(child_list)
                min_top = min(min_top, child_top)
        
        min_top = min(min_top, node_top)
    
    return min_top

def get_actual_bottom(nodes):
    """Recursively find the bottommost rendered pixel across all nodes"""
    if not nodes:
        return float('-inf')
    
    max_bottom = float('-inf')
    for node in nodes:
        # For text nodes, bottom is at y + height
        if node.type == 'text':
            node_bottom = node.y + CHAR_HEIGHT
        else:
            # For other nodes with measured height
            node_bottom = node.y + node.height
        
        if node.children:
            for child_list in node.children:
                child_bottom = get_actual_bottom(child_list)
                max_bottom = max(max_bottom, child_bottom)
        
        max_bottom = max(max_bottom, node_bottom)
    
    return max_bottom

def render_node(fb, node):
    """Render a single node at its calculated position"""
    if node.type == 'text':
        x = node.x
        for char in node.content:
            draw_char(fb, char, x, node.y)
            x += CHAR_WIDTH
    
    elif node.type == 'frac':
        # Render numerator and denominator
        render_nodes(fb, node.children[0])
        render_nodes(fb, node.children[1])
        
        # Draw fraction line
        line_y = node.y + node.baseline
        fb.hline(node.x + 2, line_y, node.width - 4, 1)
    
    elif node.type == 'exp':
        # Render exponent content
        render_nodes(fb, node.children[0])
    
    elif node.type == 'sqrt':
        # Draw radical symbol spanning entire content height
        actual_top = get_actual_top(node.children[0])
        actual_bottom = get_actual_bottom(node.children[0])
        
        # Bar 1 pixel above topmost content
        bar_top_y = actual_top - 1
        
        # Tick at bottom of content (baseline of lowest element)
        tick_bottom_y = actual_bottom
        
        # Draw radical: tick, diagonal up to bar, horizontal bar
        fb.line(node.x, tick_bottom_y - 2, node.x + 2, tick_bottom_y, 1)
        fb.line(node.x + 2, tick_bottom_y, node.x + 4, bar_top_y, 1)
        fb.hline(node.x + 4, bar_top_y, node.width - 4, 1)
        
        # Render content
        render_nodes(fb, node.children[0])
    
    elif node.type == 'nroot':
        # First render the content
        render_nodes(fb, node.children[1])
        
        # Get actual content bounds
        actual_top = get_actual_top(node.children[1])
        actual_bottom = get_actual_bottom(node.children[1])
        
        order_w = sum(n.width for n in node.children[0])
        order_h = max((n.height for n in node.children[0]), default=CHAR_HEIGHT)
        order_baseline = max((n.baseline for n in node.children[0]), default=BASELINE)
        
        bar_top_y = actual_top - 1
        tick_bottom_y = actual_bottom
        
        rad_x = node.x + order_w // 2 + 2
        
        # Draw radical
        fb.line(rad_x, tick_bottom_y - 2, rad_x + 2, tick_bottom_y, 1)
        fb.line(rad_x + 2, tick_bottom_y, rad_x + 4, bar_top_y, 1)
        fb.hline(rad_x + 4, bar_top_y, node.width - (rad_x - node.x) - 4, 1)
        
        # Reposition and render root order at bottom-left
        # Position it so its bottom aligns with the tick area
        order_y = tick_bottom_y - order_h - 2
        # Update y positions of all order nodes
        for order_node in node.children[0]:
            order_node.y = order_y
        
        render_nodes(fb, node.children[0])

def render_nodes(fb, nodes):
    """Render all nodes"""
    for node in nodes:
        render_node(fb, node)

# ===== MAIN APP =====
def latex_calc():
    keypad_state_manager_reset()
    
    # Test expressions matching handwritten design
    expressions = [
        r"\frac{5+4}{3}",           # Simple fraction
        r"5^{2}",                    # Simple exponent
        r"\sqrt{\frac{5^{2}}{6}}",  # Nested: sqrt of fraction with exponent
        r"\sqrt[3]{\frac{5^{2}}{6}}", # Your exact example
        r"\frac{x^{2}+1}{2x}",       # Complex fraction
        r"\sqrt{x^{2}+y^{2}}",       # Pythagorean
    ]
    
    expr_idx = 0
    
    buffer = bytearray((128 * 64) // 8)
    fb = framebuf.FrameBuffer(buffer, 128, 64, framebuf.MONO_VLSB)
    
    def redraw():
        fb.fill(0)
        
        expr = expressions[expr_idx]
        
        # Parse
        nodes = parse_latex(expr)
        
        # Measure
        measure_nodes(nodes)
        
        # Calculate total dimensions
        total_w = sum(n.width for n in nodes)
        total_h = max((n.height for n in nodes), default=CHAR_HEIGHT)
        total_baseline = max((n.baseline for n in nodes), default=BASELINE)
        
        # Center on display
        x_start = max(0, (128 - total_w) // 2)
        y_start = max(0, (64 - total_h) // 2)
        
        # Layout
        layout_nodes(nodes, x_start, y_start, total_baseline)
        
        # Render
        render_nodes(fb, nodes)
        
        # Show expression index
        fb.text(f"{expr_idx+1}/{len(expressions)}", 0, 56, 1)
        
        display.clear_display()
        display.graphics(buffer)
    
    redraw()
    
    while True:
        inp = typer.start_typing()
        
        if inp == "back":
            current_app[0] = "home"
            current_app[1] = "root"
            break
        
        elif inp == "nav_u":
            expr_idx = (expr_idx - 1) % len(expressions)
            redraw()
        
        elif inp == "nav_d":
            expr_idx = (expr_idx + 1) % len(expressions)
            redraw()
        
        elif inp in ["alpha", "beta"]:
            from data_modules.object_handler import keypad_state_manager
            keypad_state_manager(x=inp)
    
    gc.collect()
