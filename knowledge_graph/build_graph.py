import csv
import os
import re
from pathlib import Path

from neo4j import GraphDatabase

from env_loader import load_env_file


load_env_file()


EXPECTED_COUNTS = {
    "total_nodes": 5807,
    "total_edges": 10366,
    "company_nodes": 5470,
    "industry_nodes": 337,
    "belongs_to_edges": 5470,
    "owns_shares_edges": 1464,
    "guarantees_edges": 3432,
}


def _clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text if text != "" else None


def _clean_bool(value):
    text = _clean_text(value)
    if text is None:
        return None
    if text in {"True", "true", "1"}:
        return True
    if text in {"False", "false", "0"}:
        return False
    return None


def _clean_int(value):
    text = _clean_text(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _clean_float(value):
    text = _clean_text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _batched(items, batch_size):
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def _load_nodes(nodes_csv_path: Path):
    rows = []
    with nodes_csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            node_id = _clean_text(row.get("id:ID"))
            if not node_id:
                continue
            rows.append(
                {
                    "id": node_id,
                    "label": _clean_text(row.get(":LABEL")),
                    "node_type": _clean_text(row.get("node_type")),
                    "name": _clean_text(row.get("name")),
                    "ts_code": _clean_text(row.get("ts_code")),
                    "industry": _clean_text(row.get("industry")),
                    "industry_name": _clean_text(row.get("industry_name")),
                    "is_st": _clean_bool(row.get("is_st:boolean")),
                    "company_count": _clean_int(row.get("company_count:long")),
                }
            )
    return rows


def _load_relationships(relationships_csv_path: Path):
    rows = []
    with relationships_csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            start_id = _clean_text(row.get(":START_ID"))
            end_id = _clean_text(row.get(":END_ID"))
            rel_type = _clean_text(row.get(":TYPE"))
            if not start_id or not end_id or not rel_type:
                continue
            rows.append(
                {
                    "start_id": start_id,
                    "end_id": end_id,
                    "type": rel_type,
                    "relation": _clean_text(row.get("relation")),
                    "share_ratio": _clean_float(row.get("share_ratio:double")),
                    "share_amount": _clean_float(row.get("share_amount:double")),
                    "guarantee_count": _clean_float(row.get("guarantee_count:double")),
                    "guarantee_amount": _clean_float(row.get("guarantee_amount:double")),
                    "same_controller": _clean_bool(row.get("same_controller:boolean")),
                    "source": _clean_text(row.get("source")),
                    "report_date": _clean_text(row.get("report_date")),
                }
            )
    return rows


def _parse_expected_counts(report_path: Path):
    if not report_path.exists():
        return EXPECTED_COUNTS.copy()

    text = report_path.read_text(encoding="utf-8", errors="ignore")
    patterns = {
        "total_nodes": r"Total nodes:\s*(\d+)",
        "company_nodes": r"Company nodes:\s*(\d+)",
        "industry_nodes": r"Industry nodes:\s*(\d+)",
        "total_edges": r"Total edges:\s*(\d+)",
        "owns_shares_edges": r"OWNS_SHARES edges:\s*(\d+)",
        "guarantees_edges": r"GUARANTEES edges:\s*(\d+)",
        "belongs_to_edges": r"belongs_to edges:\s*(\d+)",
    }

    expected = EXPECTED_COUNTS.copy()
    for key, pattern in patterns.items():
        m = re.search(pattern, text)
        if m:
            expected[key] = int(m.group(1))
    return expected


class RealGraphImporter:
    def __init__(self, uri, user, password, csv_dir: Path, stats_report: Path):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.csv_dir = csv_dir
        self.stats_report = stats_report

    def close(self):
        self.driver.close()

    def cleanup_database(self):
        print("[1/6] 清理数据库中现有图数据...")
        query = """
        MATCH (n)
        CALL {
          WITH n
          DETACH DELETE n
        } IN TRANSACTIONS OF 10000 ROWS
        """
        with self.driver.session() as session:
            session.run(query)
        print("✅ 数据库清理完成")

    def ensure_constraints(self):
        print("[2/6] 创建约束...")
        query = """
        CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
        FOR (n:Entity) REQUIRE n.id IS UNIQUE
        """
        with self.driver.session() as session:
            session.run(query)
        print("✅ 约束创建完成: Entity(id) unique")

    def import_nodes(self, batch_size=5000):
        print("[3/6] 导入节点...")
        nodes_path = self.csv_dir / "nodes.csv"
        nodes = _load_nodes(nodes_path)

        query = """
        UNWIND $batch AS row
        MERGE (n:Entity {id: row.id})
        SET n.node_type = row.node_type,
            n.name = row.name,
            n.ts_code = row.ts_code,
            n.industry = row.industry,
            n.industry_name = row.industry_name,
            n.is_st = row.is_st,
            n.company_count = row.company_count
        FOREACH (_ IN CASE WHEN row.label = 'Company' THEN [1] ELSE [] END | SET n:Company)
        FOREACH (_ IN CASE WHEN row.label = 'Industry' THEN [1] ELSE [] END | SET n:Industry)
        """

        with self.driver.session() as session:
            for batch in _batched(nodes, batch_size):
                session.run(query, batch=batch)

        print(f"✅ 节点导入完成: {len(nodes)}")
        return len(nodes)

    def _import_relationship_type(self, rel_rows, rel_type, query, batch_size=5000):
        if not rel_rows:
            print(f"✅ 关系导入完成 {rel_type}: 0")
            return 0

        with self.driver.session() as session:
            for batch in _batched(rel_rows, batch_size):
                session.run(query, batch=batch)

        print(f"✅ 关系导入完成 {rel_type}: {len(rel_rows)}")
        return len(rel_rows)

    def import_relationships(self, batch_size=5000):
        print("[4/6] 导入关系...")
        rels_path = self.csv_dir / "relationships.csv"
        rels = _load_relationships(rels_path)

        belongs_rows = [r for r in rels if r["type"] == "belongs_to"]
        owns_rows = [r for r in rels if r["type"] == "OWNS_SHARES"]
        guarantees_rows = [r for r in rels if r["type"] == "GUARANTEES"]

        belongs_query = """
        UNWIND $batch AS row
        MATCH (s:Entity {id: row.start_id})
        MATCH (t:Entity {id: row.end_id})
        MERGE (s)-[r:belongs_to]->(t)
        SET r.relation = 'belongs_to',
            r.source = row.source,
            r.report_date = row.report_date
        """

        owns_query = """
        UNWIND $batch AS row
        MATCH (s:Entity {id: row.start_id})
        MATCH (t:Entity {id: row.end_id})
        MERGE (s)-[r:OWNS_SHARES]->(t)
        SET r.relation = 'OWNS_SHARES',
            r.share_ratio = row.share_ratio,
            r.share_amount = row.share_amount,
            r.same_controller = row.same_controller,
            r.source = row.source,
            r.report_date = row.report_date
        """

        guarantees_query = """
        UNWIND $batch AS row
        MATCH (s:Entity {id: row.start_id})
        MATCH (t:Entity {id: row.end_id})
        MERGE (s)-[r:GUARANTEES]->(t)
        SET r.relation = 'GUARANTEES',
            r.guarantee_count = row.guarantee_count,
            r.guarantee_amount = row.guarantee_amount,
            r.same_controller = row.same_controller,
            r.source = row.source,
            r.report_date = row.report_date
        """

        belongs_count = self._import_relationship_type(belongs_rows, "belongs_to", belongs_query, batch_size=batch_size)
        owns_count = self._import_relationship_type(owns_rows, "OWNS_SHARES", owns_query, batch_size=batch_size)
        guarantees_count = self._import_relationship_type(guarantees_rows, "GUARANTEES", guarantees_query, batch_size=batch_size)

        return {
            "belongs_to_edges": belongs_count,
            "owns_shares_edges": owns_count,
            "guarantees_edges": guarantees_count,
            "total_edges": len(rels),
        }

    def collect_stats(self):
        print("[5/6] 收集导入后统计...")
        queries = {
            "total_nodes": "MATCH (n) RETURN count(n) AS c",
            "total_edges": "MATCH ()-[r]->() RETURN count(r) AS c",
            "company_nodes": "MATCH (n:Company) RETURN count(n) AS c",
            "industry_nodes": "MATCH (n:Industry) RETURN count(n) AS c",
            "belongs_to_edges": "MATCH ()-[r:belongs_to]->() RETURN count(r) AS c",
            "owns_shares_edges": "MATCH ()-[r:OWNS_SHARES]->() RETURN count(r) AS c",
            "guarantees_edges": "MATCH ()-[r:GUARANTEES]->() RETURN count(r) AS c",
        }

        stats = {}
        with self.driver.session() as session:
            for key, query in queries.items():
                record = session.run(query).single()
                stats[key] = int(record["c"]) if record else 0
        return stats

    def validate(self, actual_stats):
        print("[6/6] 校验统计（对比 graph_stats_report 基准）...")
        expected = _parse_expected_counts(self.stats_report)

        all_passed = True
        for key in [
            "total_nodes",
            "total_edges",
            "company_nodes",
            "industry_nodes",
            "belongs_to_edges",
            "owns_shares_edges",
            "guarantees_edges",
        ]:
            expected_value = expected.get(key)
            actual_value = actual_stats.get(key, 0)
            diff = actual_value - expected_value
            ratio = abs(diff) / expected_value if expected_value else 0
            ok = ratio <= 0.01
            all_passed = all_passed and ok

            status = "PASS" if ok else "WARN"
            print(
                f"[{status}] {key}: actual={actual_value}, expected={expected_value}, "
                f"diff={diff}, diff_ratio={ratio:.2%}"
            )

        return all_passed


def main():
    base_dir = Path(__file__).resolve().parent
    csv_dir = Path(os.getenv("CSV_DIR", base_dir / "data" / "neo4j_import"))
    stats_report = base_dir / "data" / "graph_stats_report.txt"

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")

    nodes_path = csv_dir / "nodes.csv"
    rels_path = csv_dir / "relationships.csv"

    if not nodes_path.exists() or not rels_path.exists():
        raise FileNotFoundError(
            f"未找到导入文件，请检查路径: {nodes_path.as_posix()} 与 {rels_path.as_posix()}"
        )

    print("🚀 开始执行真实数据导入流程（默认：清理后全量导入）")
    importer = RealGraphImporter(
        uri=neo4j_uri,
        user=neo4j_user,
        password=neo4j_password,
        csv_dir=csv_dir,
        stats_report=stats_report,
    )

    try:
        importer.cleanup_database()
        importer.ensure_constraints()
        importer.import_nodes()
        importer.import_relationships()
        actual_stats = importer.collect_stats()
        passed = importer.validate(actual_stats)

        print("\n=== 导入后统计 ===")
        for key, value in actual_stats.items():
            print(f"- {key}: {value}")

        if not passed:
            raise RuntimeError("导入完成，但统计校验未通过（超出 1% 阈值）。")

        print("\n✅ 导入与校验全部完成")
    finally:
        importer.close()
        print("🔌 数据库连接已关闭")


if __name__ == "__main__":
    main()