"""Small helpers for inspecting uiautomator XML snapshots."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


class UiParseError(ValueError):
    """Raised when a UI node contains an invalid or missing bounds value."""


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)


@dataclass(frozen=True)
class UiNode:
    text: str
    resource_id: str
    content_desc: str
    class_name: str
    bounds: Bounds
    clickable: bool
    enabled: bool
    scrollable: bool


_BOUNDS_RE = re.compile(r"^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$")


def parse_bounds(value: str) -> Bounds:
    """Parse Android's ``[left,top][right,bottom]`` notation."""
    match = _BOUNDS_RE.fullmatch(value)
    if match is None:
        raise UiParseError(f"Invalid bounds: {value!r}")
    left, top, right, bottom = (int(part) for part in match.groups())
    if right < left or bottom < top:
        raise UiParseError(f"Reversed bounds: {value!r}")
    return Bounds(left, top, right, bottom)


def _bool_attribute(element: ET.Element, name: str) -> bool:
    return element.attrib.get(name, "false").lower() == "true"


def parse_nodes(xml_path: Path) -> list[UiNode]:
    """Return all ``node`` elements in document order."""
    root = ET.parse(xml_path).getroot()
    nodes: list[UiNode] = []
    for element in root.iter("node"):
        nodes.append(
            UiNode(
                text=element.attrib.get("text", ""),
                resource_id=element.attrib.get("resource-id", ""),
                content_desc=element.attrib.get("content-desc", ""),
                class_name=element.attrib.get("class", ""),
                bounds=parse_bounds(element.attrib.get("bounds", "")),
                clickable=_bool_attribute(element, "clickable"),
                enabled=_bool_attribute(element, "enabled"),
                scrollable=_bool_attribute(element, "scrollable"),
            )
        )
    return nodes


def find_node(
    nodes: list[UiNode],
    *,
    text: str | None = None,
    resource_id: str | None = None,
    content_desc: str | None = None,
    class_name: str | None = None,
    clickable: bool | None = None,
    enabled: bool | None = None,
    scrollable: bool | None = None,
) -> UiNode | None:
    """Find the first node matching every supplied exact attribute."""
    for node in nodes:
        if text is not None and node.text != text:
            continue
        if resource_id is not None and node.resource_id != resource_id:
            continue
        if content_desc is not None and node.content_desc != content_desc:
            continue
        if class_name is not None and node.class_name != class_name:
            continue
        if clickable is not None and node.clickable != clickable:
            continue
        if enabled is not None and node.enabled != enabled:
            continue
        if scrollable is not None and node.scrollable != scrollable:
            continue
        return node
    return None


def first_text_node(nodes: list[UiNode], candidates: tuple[str, ...]) -> UiNode | None:
    """Return the first enabled node whose text is in ``candidates``.

    Older Android list rows often expose a full-row TextView with useful bounds
    while reporting ``clickable=false``.  Tapping the node's center still
    activates the containing list item.
    """
    for candidate in candidates:
        node = find_node(nodes, text=candidate, enabled=True)
        if node is not None:
            return node
    return None


def first_scrollable(nodes: list[UiNode]) -> UiNode | None:
    """Return the first enabled scrollable node."""
    return find_node(nodes, scrollable=True, enabled=True)
