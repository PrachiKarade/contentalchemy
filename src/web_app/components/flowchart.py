
"""Tiny flowchart renderer: HTML boxes on a grid, SVG connectors underneath, hover popovers.

A diagram is {"nodes": {...}, "edges": [...]}.

node: {"row", "col", "title", "sub"?, "kind", "details"?: [str], "width"?}
    col 0 / 1 / 2 are the left, centre and right columns (fractions allowed, e.g. 0.5).
    kind: input | agent | tool | side | interrupt | store | result
    details are shown in a popover when the user hovers the box.

edge: {"from", "to", "label"?, "route"?, "dx"?, "label_at"?}
    route (picked automatically when omitted):
        straight  same column, top to bottom
        elbow     down, across, down (fan-out / fan-in)
        side      out of the box's outer edge, along the canvas margin, into the target's side
        loop      dashed loop on the right, back up to an earlier box (or the same box)
        across    horizontal, box to box on the same row
    dx shifts where the arrow lands on the target's top edge (fan-in arrows).
    label_pos "upper" lifts a straight edge's label above a fan-in merge line; label_at sets (x, y).

Styles live in static/styles.css (.ca-fc-*).
"""

import base64
from html import escape

WIDTH = 800
COLUMNS = [138, 400, 662]
ROW = 88
TOP = 16
NODE_HEIGHT = 54
NODE_WIDTH = {"agent": 256, "interrupt": 330, "input": 256, "result": 256, "store": 256, "tool": 206, "side": 206}
LANE = 12  # canvas margin used by side routes
LOOP_OUT = 40  # how far loops swing to the right
EDGE_COLOR = "#8B8FB5"
LOOP_COLOR = "#A78BFA"


def column_x(col: float) -> float:
    whole = int(col)
    if whole == col or whole >= len(COLUMNS) - 1:
        return COLUMNS[min(whole, len(COLUMNS) - 1)]
    return COLUMNS[whole] + (COLUMNS[whole + 1] - COLUMNS[whole]) * (col - whole)


def box(node: dict) -> dict:
    width = node.get("width") or NODE_WIDTH[node["kind"]]
    cx = column_x(node["col"])
    top = TOP + node["row"] * ROW
    return {"cx": cx, "top": top, "left": cx - width / 2, "right": cx + width / 2, "bottom": top + NODE_HEIGHT,
            "cy": top + NODE_HEIGHT / 2, "width": width}


def arrow_head(x: float, y: float, direction: str, color: str) -> str:
    size = 5.5
    points = {
        "down": f"{x - size},{y - size * 1.4} {x + size},{y - size * 1.4} {x},{y}",
        "right": f"{x - size * 1.4},{y - size} {x - size * 1.4},{y + size} {x},{y}",
        "left": f"{x + size * 1.4},{y - size} {x + size * 1.4},{y + size} {x},{y}",
    }[direction]
    return f'<polygon points="{points}" fill="{color}"/>'


def label_svg(x: float, y: float, text: str, anchor: str = "start", color: str = "#5B5A7A") -> str:
    return (
        # Inline font attributes: page CSS doesn't reach inside an SVG drawn as an <img>.
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{color}" '
        f'font-family="Segoe UI, Inter, Helvetica, Arial, sans-serif" font-size="11" font-weight="500" '
        f'stroke="#FFFFFF" stroke-width="5" paint-order="stroke" stroke-linejoin="round">{escape(text)}</text>'
    )


def edge_svg(edge: dict, boxes: dict) -> str:
    source, target = boxes[edge["from"]], boxes[edge["to"]]
    route = edge.get("route")
    if not route:
        if edge["from"] == edge["to"] or target["top"] < source["top"]:
            route = "loop"
        elif source["top"] == target["top"]:
            route = "across"
        elif abs(source["cx"] - target["cx"]) < 1:
            route = "straight"
        else:
            route = "elbow"

    color = LOOP_COLOR if route == "loop" else EDGE_COLOR
    dash = ' stroke-dasharray="6 5"' if route == "loop" else ""
    label = edge.get("label", "")
    parts = []

    if route == "straight":
        x, y1, y2 = source["cx"], source["bottom"], target["top"]
        points, head = [(x, y1), (x, y2 - 1)], arrow_head(x, y2, "down", color)
        # "upper" keeps the label clear of a fan-in merge line crossing the middle of the gap.
        label_y = y1 + (y2 - y1) / 4 + 4 if edge.get("label_pos") == "upper" else (y1 + y2) / 2 + 4
        label_xy = (x + 10, label_y)
    elif route == "elbow":
        tx = target["cx"] + edge.get("dx", 0)
        mid = (source["bottom"] + target["top"]) / 2
        points = [(source["cx"], source["bottom"]), (source["cx"], mid), (tx, mid), (tx, target["top"] - 1)]
        head = arrow_head(tx, target["top"], "down", color)
        label_xy = (tx + 10, (mid + target["top"]) / 2 + 5)
    elif route == "side":
        going_right = source["cx"] < target["cx"]
        lane = LANE if going_right else WIDTH - LANE
        start_x = source["left"] if going_right else source["right"]
        end_x = target["left"] if going_right else target["right"]
        points = [(start_x, source["cy"]), (lane, source["cy"]), (lane, target["cy"]), (end_x, target["cy"])]
        head = arrow_head(end_x, target["cy"], "right" if going_right else "left", color)
        label_xy = (lane + (8 if going_right else -8), target["cy"] - 10)
    elif route == "across":
        going_right = source["cx"] < target["cx"]
        start_x = source["right"] if going_right else source["left"]
        end_x = target["left"] if going_right else target["right"]
        points = [(start_x, source["cy"]), (end_x, target["cy"])]
        head = arrow_head(end_x, target["cy"], "right" if going_right else "left", color)
        label_xy = ((start_x + end_x) / 2, source["cy"] - 8)
    else:  # loop
        if edge["from"] == edge["to"]:
            right, y1, y2 = source["right"], source["cy"] - 12, source["cy"] + 12
            out = right + LOOP_OUT * 0.75
            points = [(right, y2), (out, y2), (out, y1), (right + 1, y1)]
            head = arrow_head(right, y1, "left", color)
            label_xy = (out + 6, source["cy"] + 4)
        else:
            out = max(source["right"], target["right"]) + LOOP_OUT
            points = [(source["right"], source["cy"]), (out, source["cy"]), (out, target["cy"]), (target["right"] + 1, target["cy"])]
            head = arrow_head(target["right"], target["cy"], "left", color)
            label_xy = (out + 6, (source["cy"] + target["cy"]) / 2 + 4)

    path = " ".join(f"{x},{y}" for x, y in points)
    parts.append(f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="1.8"{dash}/>')
    parts.append(head)
    if label:
        x, y = edge.get("label_at", label_xy)
        anchor = "middle" if route == "across" else ("end" if route == "side" and label_xy[0] > WIDTH / 2 else "start")
        parts.append(label_svg(x, y, label, anchor, LOOP_COLOR if route == "loop" else "#5B5A7A"))
    return "".join(parts)


def node_html(node_id: str, node: dict, geometry: dict) -> str:
    details = node.get("details", [])
    side = "left" if geometry["cx"] > WIDTH * 0.6 else "right"
    tip = ""
    if details:
        items = "".join(f"<li>{escape(item)}</li>" for item in details)
        tip = (
            f'<div class="ca-fc-tip ca-fc-tip-{side}">'
            f'<div class="ca-fc-tip-title">{escape(node["title"])}</div><ul>{items}</ul></div>'
        )
    sub = f'<div class="ca-fc-sub">{escape(node["sub"])}</div>' if node.get("sub") else ""
    info = '<span class="ca-fc-info">ⓘ</span>' if details else ""
    style = (
        f'left:{geometry["left"]}px;top:{geometry["top"]}px;width:{geometry["width"]}px;height:{NODE_HEIGHT}px;'
    )
    return (
        f'<div class="ca-fc-node ca-fc-{node["kind"]}" style="{style}" data-node="{escape(node_id)}">'
        f'<div class="ca-fc-title">{escape(node["title"])}{info}</div>{sub}{tip}</div>'
    )


def render_flowchart(diagram: dict) -> str:
    nodes = diagram["nodes"]
    boxes = {node_id: box(node) for node_id, node in nodes.items()}
    rows = max(node["row"] for node in nodes.values()) + 1
    height = TOP + rows * ROW

    edges = "".join(edge_svg(edge, boxes) for edge in diagram["edges"])
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}">{edges}</svg>'
    )
    # st.html sanitizes with DOMPurify's HTML-only profile, which strips inline <svg>.
    # An <img> with an SVG data URI survives, so the connectors are drawn as an image under the boxes.
    data_uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
    boxes_html = "".join(node_html(node_id, node, boxes[node_id]) for node_id, node in nodes.items())
    return (
        f'<div class="ca-fc-scroll"><div class="ca-fc" style="width:{WIDTH}px;height:{height}px">'
        f'<img class="ca-fc-edges" src="{data_uri}" width="{WIDTH}" height="{height}" alt="">'
        f"{boxes_html}</div></div>"
    )
