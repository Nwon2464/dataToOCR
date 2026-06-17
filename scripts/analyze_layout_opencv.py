"""Standalone OpenCV page layout experiment.

Run from the project root:
    python scripts/analyze_layout_opencv.py data/pages/<document_id>/page_0001.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


MISSING_OPENCV_MESSAGE = "opencv-python is required for this experiment."
Box = tuple[int, int, int, int]
Point = tuple[int, int]


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("Expected true or false.")


def box_to_dict(box: Box) -> dict[str, int]:
    x, y, width, height = box
    return {"x": x, "y": y, "width": width, "height": height}


def contour_boxes(
    cv2: Any,
    contours: list[Any],
    min_area: float,
    min_width: int = 1,
    min_height: int = 1,
) -> list[tuple[int, int, int, int]]:
    boxes: list[Box] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area = width * height
        if area >= min_area and width >= min_width and height >= min_height:
            boxes.append((int(x), int(y), int(width), int(height)))
    return sorted(boxes, key=lambda box: (box[1], box[0], box[2] * box[3]))


def draw_boxes(
    cv2: Any,
    image: Any,
    boxes: list[Box],
    color: tuple[int, int, int],
    label: str | None = None,
) -> Any:
    output = image.copy()
    for index, (x, y, width, height) in enumerate(boxes, start=1):
        cv2.rectangle(output, (x, y), (x + width, y + height), color, 2)
        if label:
            cv2.putText(
                output,
                f"{label}{index}",
                (x, max(12, y - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )
    return output


def inner_bounds(width: int, height: int, margin_ratio: float = 0.04) -> Box:
    margin_x = int(width * margin_ratio)
    margin_y = int(height * margin_ratio)
    return (margin_x, margin_y, width - (margin_x * 2), height - (margin_y * 2))


def box_center(box: Box) -> Point:
    x, y, width, height = box
    return (x + width // 2, y + height // 2)


def box_area(box: Box) -> int:
    return box[2] * box[3]


def boxes_overlap(a: Box, b: Box, padding: int = 0) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (
        ax - padding < bx + bw
        and ax + aw + padding > bx
        and ay - padding < by + bh
        and ay + ah + padding > by
    )


def box_inside_region(box: Box, region: Box) -> bool:
    center_x, center_y = box_center(box)
    x, y, width, height = region
    return x <= center_x <= x + width and y <= center_y <= y + height


def is_page_border_rectangle(box: Box, image_width: int, image_height: int, edge_margin_ratio: float = 0.03) -> bool:
    x, y, width, height = box
    edge_x = image_width * edge_margin_ratio
    edge_y = image_height * edge_margin_ratio
    nearly_full_page = width > image_width * 0.90 and height > image_height * 0.90
    touches_all_edges = (
        x <= edge_x
        and y <= edge_y
        and x + width >= image_width - edge_x
        and y + height >= image_height - edge_y
    )
    return nearly_full_page or touches_all_edges


def is_scan_border_line(box: Box, image_width: int, image_height: int, edge_margin_ratio: float = 0.03) -> bool:
    x, y, width, height = box
    edge_x = int(image_width * edge_margin_ratio)
    edge_y = int(image_height * edge_margin_ratio)
    is_horizontal = width >= height
    is_vertical = height > width

    # Page borders and scan edges can dominate morphology output, but they are not layout content.
    if is_horizontal and (y <= edge_y or y + height >= image_height - edge_y):
        return True
    if is_vertical and (x <= edge_x or x + width >= image_width - edge_x):
        return True
    if is_horizontal and width > image_width * 0.92 and (y <= edge_y * 2 or y + height >= image_height - edge_y * 2):
        return True
    if is_vertical and height > image_height * 0.92 and (x <= edge_x * 2 or x + width >= image_width - edge_x * 2):
        return True
    return False


def filter_line_boxes(
    boxes: list[Box],
    image_width: int,
    image_height: int,
    inner_region: Box,
) -> tuple[list[Box], list[Box]]:
    kept: list[Box] = []
    ignored: list[Box] = []
    for box in boxes:
        if is_scan_border_line(box, image_width, image_height):
            ignored.append(box)
        elif box_inside_region(box, inner_region):
            kept.append(box)
    return kept, ignored


def detect_blue_regions(cv2: Any, np: Any, image: Any) -> tuple[Any, float, int, list[Box]]:
    height, width = image.shape[:2]
    image_area = width * height
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    lower_blue = np.array([85, 35, 35], dtype=np.uint8)
    upper_blue = np.array([140, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower_blue, upper_blue)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    blue_pixel_ratio = float(cv2.countNonZero(mask)) / float(image_area)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    large_boxes = contour_boxes(
        cv2,
        contours,
        min_area=max(80, image_area * 0.00012),
        min_width=max(4, width // 250),
        min_height=max(4, height // 250),
    )
    return mask, blue_pixel_ratio, len(contours), large_boxes


def detect_lines(cv2: Any, image: Any) -> tuple[Any, list[Box], list[Box]]:
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        25,
        15,
    )

    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, width // 35), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, height // 35)))

    horizontal_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    vertical_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=1)
    line_mask = cv2.bitwise_or(horizontal_mask, vertical_mask)

    h_contours, _ = cv2.findContours(horizontal_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    v_contours, _ = cv2.findContours(vertical_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    horizontal_boxes = contour_boxes(
        cv2,
        h_contours,
        min_area=max(30, width * height * 0.00001),
        min_width=max(18, width // 60),
        min_height=1,
    )
    vertical_boxes = contour_boxes(
        cv2,
        v_contours,
        min_area=max(30, width * height * 0.00001),
        min_width=1,
        min_height=max(18, height // 60),
    )
    return line_mask, horizontal_boxes, vertical_boxes


def detect_large_rectangles(
    cv2: Any,
    line_mask: Any,
    image_width: int,
    image_height: int,
) -> list[Box]:
    image_area = image_width * image_height
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    connected = cv2.dilate(line_mask, kernel, iterations=2)
    connected = cv2.morphologyEx(connected, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = contour_boxes(
        cv2,
        contours,
        min_area=image_area * 0.012,
        min_width=max(40, image_width // 20),
        min_height=max(40, image_height // 30),
    )
    return boxes


def filter_rectangles(
    rectangles: list[Box],
    image_width: int,
    image_height: int,
    inner_region: Box,
) -> tuple[list[Box], list[Box]]:
    kept: list[Box] = []
    ignored: list[Box] = []
    for rectangle in rectangles:
        if is_page_border_rectangle(rectangle, image_width, image_height):
            ignored.append(rectangle)
        elif box_inside_region(rectangle, inner_region):
            kept.append(rectangle)
    return kept, ignored


def intersection_points(horizontal_boxes: list[Box], vertical_boxes: list[Box], tolerance: int = 4) -> list[Point]:
    points: list[Point] = []
    seen: set[Point] = set()
    for hx, hy, hw, hh in horizontal_boxes:
        h_y = hy + hh // 2
        for vx, vy, vw, vh in vertical_boxes:
            v_x = vx + vw // 2
            if hx - tolerance <= v_x <= hx + hw + tolerance and vy - tolerance <= h_y <= vy + vh + tolerance:
                point = (int(v_x), int(h_y))
                if point not in seen:
                    seen.add(point)
                    points.append(point)
    return points


def spacing_regular_score(line_boxes: list[Box], axis: str) -> float:
    if len(line_boxes) < 3:
        return 0.0

    centers = sorted(box_center(box)[1 if axis == "horizontal" else 0] for box in line_boxes)
    gaps = [next_center - center for center, next_center in zip(centers, centers[1:]) if next_center - center > 2]
    if len(gaps) < 2:
        return 0.0

    mean_gap = sum(gaps) / len(gaps)
    if mean_gap <= 0:
        return 0.0

    variance = sum((gap - mean_gap) ** 2 for gap in gaps) / len(gaps)
    coefficient = (variance ** 0.5) / mean_gap
    return round(max(0.0, 1.0 - min(coefficient, 1.0)), 3)


def score_grid(
    horizontal_boxes: list[Box],
    vertical_boxes: list[Box],
    intersections: list[Point],
) -> tuple[float, float]:
    # Tables need real row/column intersections; diagrams can have many lines without grid structure.
    h_score = min(len(horizontal_boxes) / 8.0, 1.0)
    v_score = min(len(vertical_boxes) / 4.0, 1.0)
    possible_intersections = max(1, len(horizontal_boxes) * len(vertical_boxes))
    intersection_density = len(intersections) / possible_intersections
    intersection_score = min(len(intersections) / 12.0, 1.0) * min(intersection_density / 0.45, 1.0)
    h_regular = spacing_regular_score(horizontal_boxes, "horizontal")
    v_regular = spacing_regular_score(vertical_boxes, "vertical")
    line_regular_spacing_score = round((h_regular + v_regular) / 2.0, 3)
    table_grid_score = round(
        (intersection_score * 0.55)
        + (line_regular_spacing_score * 0.25)
        + (min(h_score, v_score) * 0.20),
        3,
    )
    return table_grid_score, line_regular_spacing_score


def points_inside_box(points: list[Point], box: Box, padding: int = 3) -> int:
    x, y, width, height = box
    return sum(
        1
        for point_x, point_y in points
        if x - padding <= point_x <= x + width + padding and y - padding <= point_y <= y + height + padding
    )


def table_candidate_boxes(rectangles: list[Box], intersections: list[Point], image_width: int) -> list[Box]:
    candidates: list[Box] = []
    for rectangle in rectangles:
        _, _, width, _ = rectangle
        intersection_count = points_inside_box(intersections, rectangle)
        broad_enough = width >= image_width * 0.35
        if intersection_count >= 8 and broad_enough:
            candidates.append(rectangle)
    return candidates


def isolated_line_blocks(cv2: Any, line_mask: Any, image_width: int, image_height: int, inner_region: Box) -> list[Box]:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    connected = cv2.dilate(line_mask, kernel, iterations=1)
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = contour_boxes(
        cv2,
        contours,
        min_area=max(120, image_width * image_height * 0.0015),
        min_width=max(25, image_width // 30),
        min_height=max(20, image_height // 45),
    )
    return [
        box
        for box in boxes
        if box_inside_region(box, inner_region) and not is_page_border_rectangle(box, image_width, image_height)
    ]


def diagram_candidate_boxes(
    rectangles: list[Box],
    line_blocks: list[Box],
    intersections: list[Point],
    blue_boxes: list[Box],
    image_width: int,
    image_height: int,
) -> list[Box]:
    page_area = image_width * image_height
    candidates: list[Box] = []
    for box in rectangles + line_blocks:
        x, y, width, height = box
        area_ratio = box_area(box) / page_area
        compact = width < image_width * 0.75 and height < image_height * 0.45
        medium_size = 0.004 <= area_ratio <= 0.16
        middle_or_lower = y + height / 2 >= image_height * 0.30
        low_grid = points_inside_box(intersections, box) < 8
        nearby_blue = any(boxes_overlap(box, blue_box, padding=12) for blue_box in blue_boxes)
        if medium_size and compact and middle_or_lower and (low_grid or nearby_blue):
            candidates.append(box)

    deduped: list[Box] = []
    for candidate in sorted(candidates, key=lambda item: (item[1], item[0], -box_area(item))):
        if not any(boxes_overlap(candidate, existing, padding=8) and box_area(candidate) <= box_area(existing) for existing in deduped):
            deduped.append(candidate)
    return deduped


def score_table(
    table_grid_score: float,
    line_regular_spacing_score: float,
    table_candidate_count: int,
    grid_intersection_count: int,
) -> float:
    candidate_score = min(table_candidate_count / 2.0, 1.0)
    intersection_score = min(grid_intersection_count / 16.0, 1.0)
    score = (table_grid_score * 0.60) + (line_regular_spacing_score * 0.15) + (candidate_score * 0.15) + (intersection_score * 0.10)
    return round(score, 3)


def score_diagram(
    table_grid_score: float,
    diagram_candidate_count: int,
    non_grid_rectangle_count: int,
    isolated_line_block_count: int,
    line_regular_spacing_score: float,
    blue_boxes: list[Box],
    image_width: int,
    image_height: int,
) -> tuple[float, float]:
    page_area = image_width * image_height
    candidate_signal = min(diagram_candidate_count / 2.0, 1.0)
    non_grid_signal = min(non_grid_rectangle_count / 3.0, 1.0)
    isolated_signal = min(isolated_line_block_count / 2.0, 1.0)
    irregular_signal = max(0.0, 1.0 - line_regular_spacing_score)
    blue_box_signal = min(len(blue_boxes) / 4.0, 1.0)
    sparse_blue_signal = 0.0

    for _, _, width, height in blue_boxes:
        area_ratio = (width * height) / page_area
        if 0.0002 <= area_ratio <= 0.08:
            sparse_blue_signal += 0.15

    # Compact non-grid line blocks often mean diagrams: boxes, arrows, callouts, or flow shapes.
    diagram_structure_score = round(
        (candidate_signal * 0.40)
        + (non_grid_signal * 0.20)
        + (isolated_signal * 0.15)
        + (irregular_signal * 0.15)
        + (min(sparse_blue_signal, 0.20) * 0.10)
        + (blue_box_signal * 0.05),
        3,
    )
    grid_penalty = max(0.25, 1.0 - (table_grid_score * 0.75))
    diagram_score = round(min(diagram_structure_score * grid_penalty, 1.0), 3)
    return diagram_score, diagram_structure_score


def suggest_layout(
    table_score: float,
    table_grid_score: float,
    grid_intersection_count: int,
    line_regular_spacing_score: float,
    diagram_score: float,
    diagram_structure_score: float,
    possible_table: bool,
    possible_diagram: bool,
    blue_boxes: list[Box],
) -> tuple[str, float, bool, bool]:
    sidebar_like_boxes = [box for box in blue_boxes if box[0] < 120 or box[2] < 180]
    table_clearly_exceeds_diagram = table_score >= diagram_score + 0.15
    has_table = (
        table_grid_score >= 0.62
        and grid_intersection_count >= 12
        and line_regular_spacing_score >= 0.45
        and table_score >= 0.62
        and table_clearly_exceeds_diagram
    )
    has_diagram = (
        (diagram_score >= 0.65 or diagram_structure_score >= 0.75)
        and table_grid_score < 0.65
    )

    if has_table and has_diagram:
        confidence = min(max(table_score, diagram_score), 0.90)
        return "mixed", round(confidence, 3), has_table, has_diagram
    if has_table:
        return "table", round(min(table_score, 0.95), 3), has_table, has_diagram
    if has_diagram:
        return "diagram", round(min(diagram_score, 0.90), 3), has_table, has_diagram
    if not has_table and possible_diagram and diagram_score > table_score:
        return "mixed", round(max(0.35, min(diagram_score * 0.80, 0.50)), 3), has_table, has_diagram
    if possible_table and possible_diagram:
        return "mixed", round(max(table_score, diagram_score) * 0.70, 3), has_table, has_diagram
    if table_score >= 0.40 and diagram_score >= 0.35:
        return "mixed", round(max(table_score, diagram_score) * 0.75, 3), has_table, has_diagram
    if sidebar_like_boxes and diagram_score < 0.35 and table_score < 0.35:
        return "text_with_sidebar", 0.55, has_table, has_diagram
    if table_score < 0.25 and diagram_score < 0.25:
        return "text", round(1.0 - max(table_score, diagram_score), 3), has_table, has_diagram
    return "unknown", round(max(table_score, diagram_score) * 0.60, 3), has_table, has_diagram


def layout_risk_flags(
    table_score: float,
    table_grid_score: float,
    grid_intersection_count: int,
    line_regular_spacing_score: float,
    diagram_score: float,
    diagram_structure_score: float,
    diagram_candidate_count: int,
    isolated_line_block_count: int,
) -> tuple[bool, bool, str, list[str]]:
    risk_reasons: list[str] = []

    possible_table = False
    if table_grid_score >= 0.45:
        possible_table = True
        risk_reasons.append("table_grid_score >= 0.45")
    if grid_intersection_count >= 8 and line_regular_spacing_score >= 0.35:
        possible_table = True
        risk_reasons.append("grid_intersection_count >= 8 and line_regular_spacing_score >= 0.35")
    if table_score >= 0.45 and table_score > diagram_score + 0.10:
        possible_table = True
        risk_reasons.append("table_score >= 0.45 and table_score > diagram_score + 0.10")

    possible_diagram = False
    if diagram_candidate_count >= 1:
        possible_diagram = True
        risk_reasons.append("diagram_candidate_count >= 1")
    if diagram_score >= 0.40:
        possible_diagram = True
    if diagram_candidate_count >= 1 and diagram_structure_score >= 0.45:
        possible_diagram = True
        risk_reasons.append("diagram_structure_score >= 0.45")
    if diagram_candidate_count >= 1 and diagram_score > table_score:
        possible_diagram = True
        risk_reasons.append("diagram_score > table_score")
    if isolated_line_block_count >= 1 and table_grid_score < 0.45:
        possible_diagram = True
        risk_reasons.append("compact non-grid line/box block exists")
    if diagram_score >= 0.40 and table_grid_score < 0.45:
        possible_diagram = True
        risk_reasons.append("diagram_score >= 0.40 and table_grid_score < 0.45")
    if possible_diagram and table_grid_score < 0.45:
        risk_reasons.append("table_grid_score is not high enough for a real table")

    if possible_table and possible_diagram:
        layout_risk = "high"
    elif possible_diagram and (diagram_score >= 0.40 or diagram_structure_score >= 0.45):
        layout_risk = "medium"
    elif possible_table or possible_diagram:
        layout_risk = "low"
    else:
        layout_risk = "none"

    return possible_table, possible_diagram, layout_risk, risk_reasons


def expected_page_policy(possible_diagram: bool, layout_risk: str) -> dict[str, bool | str]:
    if possible_diagram and layout_risk in {"medium", "high"}:
        return {
            "main_text_policy": "use_for_auto_text",
            "diagram_policy": "separate_as_diagram_block",
            "manual_review_recommended": True,
            "auto_text_note": "Add 【図解あり】 and preserve diagram text separately",
        }
    return {
        "main_text_policy": "use_for_auto_text",
        "diagram_policy": "merge_with_main_text",
        "manual_review_recommended": False,
        "auto_text_note": "",
    }


def output_stem(image_path: Path) -> str:
    return f"{image_path.stem}_layout"


def analyze(image_path: Path, out_dir: Path, show_boxes: bool) -> int:
    try:
        import cv2
        import numpy as np
    except ImportError:
        print(MISSING_OPENCV_MESSAGE)
        return 1

    if not image_path.exists():
        print(f"Error: image file not found: {image_path}")
        return 1

    image = cv2.imread(str(image_path))
    if image is None:
        print(f"Error: image could not be loaded: {image_path}")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    height, width = image.shape[:2]
    aspect_ratio = width / height if height else 0.0
    content_region = inner_bounds(width, height)

    blue_mask, blue_pixel_ratio, blue_contour_count, blue_boxes = detect_blue_regions(cv2, np, image)
    line_mask, horizontal_boxes, vertical_boxes = detect_lines(cv2, image)
    raw_rectangle_boxes = detect_large_rectangles(cv2, line_mask, width, height)
    inner_horizontal_boxes, ignored_horizontal_boxes = filter_line_boxes(horizontal_boxes, width, height, content_region)
    inner_vertical_boxes, ignored_vertical_boxes = filter_line_boxes(vertical_boxes, width, height, content_region)
    rectangle_boxes, ignored_rectangle_boxes = filter_rectangles(raw_rectangle_boxes, width, height, content_region)
    ignored_border_artifacts = ignored_horizontal_boxes + ignored_vertical_boxes + ignored_rectangle_boxes

    horizontal_line_count = len(horizontal_boxes)
    vertical_line_count = len(vertical_boxes)
    inner_horizontal_line_count = len(inner_horizontal_boxes)
    inner_vertical_line_count = len(inner_vertical_boxes)
    large_rectangle_count = len(rectangle_boxes)
    has_page_border_artifact = bool(ignored_border_artifacts)

    grid_points = intersection_points(inner_horizontal_boxes, inner_vertical_boxes)
    grid_intersection_count = len(grid_points)
    table_grid_score, line_regular_spacing_score = score_grid(inner_horizontal_boxes, inner_vertical_boxes, grid_points)
    table_candidates = table_candidate_boxes(rectangle_boxes, grid_points, width)
    line_blocks = isolated_line_blocks(cv2, line_mask, width, height, content_region)
    diagram_candidates = diagram_candidate_boxes(rectangle_boxes, line_blocks, grid_points, blue_boxes, width, height)
    non_grid_rectangle_count = sum(1 for box in rectangle_boxes if points_inside_box(grid_points, box) < 8)
    isolated_line_block_count = len(line_blocks)
    diagram_candidate_count = len(diagram_candidates)
    table_score = score_table(
        table_grid_score,
        line_regular_spacing_score,
        len(table_candidates),
        grid_intersection_count,
    )
    diagram_score, diagram_structure_score = score_diagram(
        table_grid_score,
        diagram_candidate_count,
        non_grid_rectangle_count,
        isolated_line_block_count,
        line_regular_spacing_score,
        blue_boxes,
        width,
        height,
    )
    possible_table, possible_diagram, layout_risk, risk_reasons = layout_risk_flags(
        table_score,
        table_grid_score,
        grid_intersection_count,
        line_regular_spacing_score,
        diagram_score,
        diagram_structure_score,
        diagram_candidate_count,
        isolated_line_block_count,
    )
    suggested_layout, suggested_layout_confidence, has_table, has_diagram = suggest_layout(
        table_score,
        table_grid_score,
        grid_intersection_count,
        line_regular_spacing_score,
        diagram_score,
        diagram_structure_score,
        possible_table,
        possible_diagram,
        blue_boxes,
    )
    has_blue_regions = blue_pixel_ratio > 0.002 or bool(blue_boxes)
    page_policy = expected_page_policy(possible_diagram, layout_risk)

    stem = output_stem(image_path)
    blue_mask_path = out_dir / f"{stem}_blue_mask.png"
    blue_boxes_path = out_dir / f"{stem}_blue_boxes.png"
    line_mask_path = out_dir / f"{stem}_line_mask.png"
    line_boxes_path = out_dir / f"{stem}_line_boxes.png"
    table_candidates_path = out_dir / f"{stem}_table_candidates.png"
    diagram_candidates_path = out_dir / f"{stem}_diagram_candidates.png"
    ignored_borders_path = out_dir / f"{stem}_ignored_borders.png"
    grid_intersections_path = out_dir / f"{stem}_grid_intersections.png"
    report_path = out_dir / f"{stem}_report.json"

    cv2.imwrite(str(blue_mask_path), blue_mask)
    cv2.imwrite(str(line_mask_path), line_mask)

    blue_overlay = draw_boxes(cv2, image, blue_boxes, (255, 0, 0), "blue-" if show_boxes else None)
    cv2.imwrite(str(blue_boxes_path), blue_overlay)

    line_overlay = image.copy()
    line_overlay = draw_boxes(cv2, line_overlay, inner_horizontal_boxes, (0, 255, 0), "h-" if show_boxes else None)
    line_overlay = draw_boxes(cv2, line_overlay, inner_vertical_boxes, (0, 0, 255), "v-" if show_boxes else None)
    line_overlay = draw_boxes(cv2, line_overlay, rectangle_boxes, (0, 255, 255), "rect-" if show_boxes else None)
    cv2.imwrite(str(line_boxes_path), line_overlay)

    table_overlay = draw_boxes(cv2, image, table_candidates, (0, 180, 255), "table-" if show_boxes else None)
    cv2.imwrite(str(table_candidates_path), table_overlay)

    diagram_overlay = draw_boxes(cv2, image, diagram_candidates, (255, 0, 255), "diagram-" if show_boxes else None)
    cv2.imwrite(str(diagram_candidates_path), diagram_overlay)

    ignored_overlay = draw_boxes(cv2, image, ignored_border_artifacts, (128, 128, 128), "ignored-" if show_boxes else None)
    cv2.imwrite(str(ignored_borders_path), ignored_overlay)

    grid_overlay = image.copy()
    for point_x, point_y in grid_points:
        cv2.circle(grid_overlay, (point_x, point_y), 4, (0, 255, 255), -1)
    cv2.imwrite(str(grid_intersections_path), grid_overlay)

    report: dict[str, Any] = {
        "image_path": str(image_path),
        "width": width,
        "height": height,
        "aspect_ratio": round(aspect_ratio, 4),
        "blue_pixel_ratio": round(blue_pixel_ratio, 6),
        "blue_contour_count": blue_contour_count,
        "horizontal_line_count": horizontal_line_count,
        "vertical_line_count": vertical_line_count,
        "inner_horizontal_line_count": inner_horizontal_line_count,
        "inner_vertical_line_count": inner_vertical_line_count,
        "grid_intersection_count": grid_intersection_count,
        "table_grid_score": table_grid_score,
        "line_regular_spacing_score": line_regular_spacing_score,
        "non_grid_rectangle_count": non_grid_rectangle_count,
        "diagram_candidate_count": diagram_candidate_count,
        "isolated_line_block_count": isolated_line_block_count,
        "diagram_structure_score": diagram_structure_score,
        "large_rectangle_count": large_rectangle_count,
        "table_score": table_score,
        "diagram_score": diagram_score,
        "has_table": has_table,
        "has_diagram": has_diagram,
        "possible_table": possible_table,
        "possible_diagram": possible_diagram,
        "has_blue_regions": has_blue_regions,
        "has_page_border_artifact": has_page_border_artifact,
        "layout_risk": layout_risk,
        "risk_reasons": risk_reasons,
        "suggested_layout": suggested_layout,
        "suggested_layout_confidence": suggested_layout_confidence,
        "expected_page_policy": page_policy,
        "boxes": {
            "blue_regions": [box_to_dict(box) for box in blue_boxes],
            "horizontal_lines": [box_to_dict(box) for box in inner_horizontal_boxes],
            "vertical_lines": [box_to_dict(box) for box in inner_vertical_boxes],
            "large_rectangles": [box_to_dict(box) for box in rectangle_boxes],
            "table_candidates": [box_to_dict(box) for box in table_candidates],
            "diagram_candidates": [box_to_dict(box) for box in diagram_candidates],
            "ignored_border_artifacts": [box_to_dict(box) for box in ignored_border_artifacts],
        },
        "debug_outputs": {
            "blue_mask": str(blue_mask_path),
            "blue_boxes": str(blue_boxes_path),
            "line_mask": str(line_mask_path),
            "line_boxes": str(line_boxes_path),
            "table_candidates": str(table_candidates_path),
            "diagram_candidates": str(diagram_candidates_path),
            "ignored_borders": str(ignored_borders_path),
            "grid_intersections": str(grid_intersections_path),
        },
    }

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Image info")
    print(f"- image_path: {image_path}")
    print(f"- width: {width}")
    print(f"- height: {height}")
    print(f"- aspect_ratio: {aspect_ratio:.4f}")
    print()
    print("Layout analysis summary")
    print(f"- image_size: {width}x{height}")
    print(f"- blue_pixel_ratio: {blue_pixel_ratio:.3f}")
    print(f"- inner_horizontal_lines: {inner_horizontal_line_count}")
    print(f"- inner_vertical_lines: {inner_vertical_line_count}")
    print(f"- grid_intersections: {grid_intersection_count}")
    print(f"- table_grid_score: {table_grid_score:.2f}")
    print(f"- line_regular_spacing_score: {line_regular_spacing_score:.2f}")
    print(f"- diagram_structure_score: {diagram_structure_score:.2f}")
    print(f"- large_rectangles: {large_rectangle_count}")
    print(f"- non_grid_rectangles: {non_grid_rectangle_count}")
    print(f"- diagram_candidates: {diagram_candidate_count}")
    print(f"- table_score: {table_score:.2f}")
    print(f"- diagram_score: {diagram_score:.2f}")
    print(f"- has_table: {has_table}")
    print(f"- has_diagram: {has_diagram}")
    print(f"- has_page_border_artifact: {has_page_border_artifact}")
    print(f"- suggested_layout: {suggested_layout}")
    print(f"- confidence: {suggested_layout_confidence:.2f}")
    print()
    print("Layout risk")
    print(f"- possible_table: {possible_table}")
    print(f"- possible_diagram: {possible_diagram}")
    print(f"- layout_risk: {layout_risk}")
    print("- risk_reasons:")
    if risk_reasons:
        for reason in risk_reasons:
            print(f"  - {reason}")
    else:
        print("  - none")
    print()
    print(f"JSON report: {report_path}")
    print(f"Debug images: {out_dir}")

    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Analyze page layout signals from one rendered page image.")
    parser.add_argument("image_path", help="Path to rendered page image.")
    parser.add_argument("--out-dir", default="data/debug_layout", help="Directory for JSON and debug images.")
    parser.add_argument(
        "--show-boxes",
        type=parse_bool,
        default=False,
        help="Draw labels on debug box overlays. Accepts true/false.",
    )
    args = parser.parse_args(argv[1:])

    return analyze(Path(args.image_path), Path(args.out_dir), args.show_boxes)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
