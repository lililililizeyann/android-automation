from pathlib import Path

from android_auto.ui import find_node, first_text_node, parse_bounds, parse_nodes


def test_parse_bounds_center() -> None:
    bounds = parse_bounds("[10,20][110,220]")
    assert bounds.center == (60, 120)


def test_parse_nodes_and_find(tmp_path: Path) -> None:
    xml_path = tmp_path / "window.xml"
    xml_path.write_text(
        '<hierarchy><node text="Views" resource-id="id/views" '
        'content-desc="" class="android.widget.TextView" '
        'clickable="false" enabled="true" scrollable="false" '
        'bounds="[1,2][101,202]" /></hierarchy>',
        encoding="utf-8",
    )

    nodes = parse_nodes(xml_path)
    node = find_node(nodes, resource_id="id/views", clickable=False, enabled=True)

    assert node is not None
    assert node.text == "Views"
    assert node.bounds.center == (51, 102)
    assert first_text_node(nodes, ("Views",)) == node
