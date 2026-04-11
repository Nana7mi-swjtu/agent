"""
将 NetworkX node-link JSON 图渲染为可交互 HTML（PyVis）。

默认输入: data/base_graph_enriched_tushare.json
默认输出: data/graph_interactive.html

用法:
  python render_pyvis.py
  python render_pyvis.py --input data/base_graph_enriched_tushare.json --output data/graph_interactive.html
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from pyvis.network import Network
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyVis 未安装，请先执行: pip install pyvis") from exc


NODE_COLORS = {
    "company": "#3B82F6",
    "industry": "#F59E0B",
    "default": "#94A3B8",
}

EDGE_COLORS = {
    "OWNS_SHARES": "#10B981",
    "GUARANTEES": "#EF4444",
    "belongs_to": "#64748B",
    "default": "#A8A29E",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render graph JSON to interactive PyVis HTML")
    parser.add_argument("--input", default="data/base_graph_enriched_tushare.json", help="输入图 JSON")
    parser.add_argument("--output", default="data/graph_interactive.html", help="输出 HTML")
    return parser.parse_args()


def _edge_type(edge: dict) -> str:
    return str(edge.get("relation") or edge.get("type") or "default")


def main() -> None:
    args = parse_args()
    in_path = Path(args.input)
    out_path = Path(args.output)

    graph = json.loads(in_path.read_text(encoding="utf-8"))
    nodes = graph.get("nodes", [])
    edges = graph.get("links") or graph.get("edges", [])

    net = Network(height="840px", width="100%", bgcolor="#0B1020", font_color="#E5E7EB", directed=True)
    net.barnes_hut(gravity=-8000, central_gravity=0.2, spring_length=120, spring_strength=0.02, damping=0.6)

    for node in nodes:
        node_id = str(node.get("id"))
        node_type = str(node.get("node_type", "default"))
        name = str(node.get("name", node_id))
        color = NODE_COLORS.get(node_type, NODE_COLORS["default"])

        title_parts = [f"id: {node_id}", f"type: {node_type}", f"name: {name}"]
        if node_type == "company":
            title_parts.append(f"ts_code: {node.get('ts_code', '')}")
            title_parts.append(f"industry: {node.get('industry_name') or node.get('industry', '')}")
            title_parts.append(f"is_st: {node.get('is_st', False)}")

        border_width = 3 if node_type == "company" and node.get("is_st") is True else 1

        net.add_node(
            node_id,
            label=name,
            title="<br>".join(title_parts),
            color=color,
            size=20 if node_type == "industry" else 12,
            borderWidth=border_width,
            shape="dot",
        )

    for edge in edges:
        src = str(edge.get("source"))
        dst = str(edge.get("target"))
        rel = _edge_type(edge)
        color = EDGE_COLORS.get(rel, EDGE_COLORS["default"])

        detail = [f"relation: {rel}"]
        for key in ("share_ratio", "share_amount", "guarantee_count", "guarantee_amount", "same_controller", "source"):
            if key in edge:
                detail.append(f"{key}: {edge.get(key)}")

        net.add_edge(src, dst, color=color, title="<br>".join(detail), arrows="to")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    net.show(str(out_path), notebook=False)
    print(f"PyVis 可视化已生成: {out_path.as_posix()}")


if __name__ == "__main__":
    main()
