"""
将 node-link JSON 图导出为 Neo4j CSV。

默认输入: data/base_graph_enriched_tushare.json
默认输出目录: data/neo4j_import

输出:
- nodes.csv
- relationships.csv

用法:
  python export_neo4j_csv.py
  python export_neo4j_csv.py --input data/base_graph_enriched_tushare.json --output-dir data/neo4j_import
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export graph JSON to Neo4j CSV files")
    parser.add_argument("--input", default="data/base_graph_enriched_tushare.json", help="输入图 JSON")
    parser.add_argument("--output-dir", default="data/neo4j_import", help="CSV 输出目录")
    return parser.parse_args()


def _safe(value):
    if value is None:
        return ""
    return value


def main() -> None:
    args = parse_args()
    in_path = Path(args.input)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    graph = json.loads(in_path.read_text(encoding="utf-8"))
    nodes = graph.get("nodes", [])
    edges = graph.get("links") or graph.get("edges", [])

    nodes_file = out_dir / "nodes.csv"
    rels_file = out_dir / "relationships.csv"

    with nodes_file.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id:ID",
            ":LABEL",
            "node_type",
            "name",
            "ts_code",
            "industry",
            "industry_name",
            "is_st:boolean",
            "company_count:long",
        ])

        for n in nodes:
            node_type = str(n.get("node_type", "Entity"))
            label = "Company" if node_type == "company" else ("Industry" if node_type == "industry" else "Entity")
            writer.writerow([
                _safe(n.get("id")),
                label,
                node_type,
                _safe(n.get("name")),
                _safe(n.get("ts_code")),
                _safe(n.get("industry")),
                _safe(n.get("industry_name")),
                bool(n.get("is_st")) if n.get("is_st") is not None else "",
                _safe(n.get("company_count")),
            ])

    with rels_file.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            ":START_ID",
            ":END_ID",
            ":TYPE",
            "relation",
            "share_ratio:double",
            "share_amount:double",
            "guarantee_count:double",
            "guarantee_amount:double",
            "same_controller:boolean",
            "source",
            "report_date",
        ])

        for e in edges:
            rel = str(e.get("relation") or e.get("type") or "RELATED_TO")
            writer.writerow([
                _safe(e.get("source")),
                _safe(e.get("target")),
                rel,
                rel,
                _safe(e.get("share_ratio")),
                _safe(e.get("share_amount")),
                _safe(e.get("guarantee_count")),
                _safe(e.get("guarantee_amount")),
                bool(e.get("same_controller")) if e.get("same_controller") is not None else "",
                _safe(e.get("source")),
                _safe(e.get("report_date")),
            ])

    print(f"Neo4j CSV 已导出: {nodes_file.as_posix()}")
    print(f"Neo4j CSV 已导出: {rels_file.as_posix()}")


if __name__ == "__main__":
    main()
