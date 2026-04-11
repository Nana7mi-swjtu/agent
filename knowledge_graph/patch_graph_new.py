"""
独立补图入口，不修改原有脚本和原始图文件。

默认行为：
- 输入: data/base_graph.json
- 输出: data/base_graph_enriched.json

执行:
  python patch_graph_new.py
  python patch_graph_new.py --input data/base_graph.json --output data/base_graph_enriched.json
"""

from __future__ import annotations

import argparse
import os
from datetime import date

import pandas as pd
import tushare as ts

from patch_graph import (
    _normalize_name,
    _safe_float,
    build_company_maps,
    load_graph,
    patch_guarantee_edges,
    patch_owns_shares_edges,
    patch_st_labels,
    print_stats,
    save_graph,
)


def _read_tushare_token(env_path: str = ".env") -> str | None:
    if not os.path.exists(env_path):
        return None

    with open(env_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("TUSHARE_TOKEN="):
                return line.split("=", 1)[1].strip()
    return None


def _get_tushare_pro():
    token = _read_tushare_token()
    if not token:
        print("[Tushare] 未在 .env 中找到 TUSHARE_TOKEN，跳过 Tushare 增强。")
        return None
    ts.set_token(token)
    return ts.pro_api()


def _entity_key(text: str) -> str:
    s = _normalize_name(text)
    for tail in (
        "集团股份有限公司",
        "股份有限公司",
        "集团有限公司",
        "有限责任公司",
        "有限公司",
        "控股集团",
        "控股",
        "集团",
    ):
        if s.endswith(tail):
            s = s[: -len(tail)]
            break
    return s


def _fetch_top10_holders_for_period(pro, period: str, page_size: int = 5000, max_pages: int = 30):
    offset = 0
    frames = []
    page_count = 0
    while page_count < max_pages:
        df = pro.top10_holders(
            period=period,
            fields="ts_code,holder_name,hold_amount,hold_ratio,end_date",
            limit=page_size,
            offset=offset,
        )
        if df is None or df.empty:
            break
        frames.append(df)
        page_count += 1
        if len(df) < page_size:
            break
        offset += page_size

    if page_count >= max_pages:
        print(f"[Tushare-OWNS] 警告: 达到分页上限 {max_pages}，已提前停止以避免长时间卡住。")

    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def _patch_st_labels_with_tushare(graph, pro) -> tuple[int, int]:
    print("[Tushare-ST] 测试接口: pro.stock_basic")
    frames = []
    for status in ("L", "P", "D"):
        df = pro.stock_basic(list_status=status, fields="ts_code,name")
        if df is not None and not df.empty:
            frames.append(df)

    if not frames:
        print("[Tushare-ST] 未取到 stock_basic 数据，保留现有 is_st。")
        return 0, 0

    all_df = pd.concat(frames, ignore_index=True)
    st_mask = all_df["name"].astype(str).str.upper().str.contains(r"(?:^\*?ST)|S\*ST", regex=True)
    st_codes = set(all_df.loc[st_mask, "ts_code"].astype(str).str.split(".").str[0].str.zfill(6).tolist())

    patched = 0
    st_count = 0
    for _, data in graph.nodes(data=True):
        if data.get("node_type") != "company":
            continue
        code = str(data.get("ts_code", "")).split(".")[0].zfill(6)
        is_st = code in st_codes
        data["is_st"] = is_st
        data["is_st_source"] = "tushare.stock_basic"
        patched += 1
        if is_st:
            st_count += 1

    print(f"[Tushare-ST] 已覆盖更新 {patched} 家公司 is_st，命中 ST: {st_count}")
    return patched, st_count


def _patch_owns_with_tushare_top10(graph, pro, controllers_by_company: dict[str, set[str]]) -> tuple[int, int]:
    print("[Tushare-OWNS] 测试接口: pro.top10_holders")
    code_to_node, name_to_nodes = build_company_maps(graph)

    alias_to_nodes: dict[str, set[str]] = {}
    for name, nodes in name_to_nodes.items():
        key = _entity_key(name)
        if key:
            alias_to_nodes.setdefault(key, set()).update(nodes)

    stock_basic_frames = []
    for status in ("L", "P", "D"):
        sb = pro.stock_basic(list_status=status, fields="ts_code,name,fullname")
        if sb is not None and not sb.empty:
            stock_basic_frames.append(sb)

    if stock_basic_frames:
        sb_all = pd.concat(stock_basic_frames, ignore_index=True)
        for _, row in sb_all.iterrows():
            code = str(row.get("ts_code", "")).split(".")[0].zfill(6)
            node = code_to_node.get(code)
            if not node:
                continue
            for field in ("name", "fullname"):
                key = _entity_key(str(row.get(field, "")))
                if key:
                    alias_to_nodes.setdefault(key, set()).add(node)

    current_year = date.today().year
    periods = [
        f"{current_year - 1}1231",
        f"{current_year - 1}0930",
        f"{current_year - 1}0630",
        f"{current_year - 1}0331",
        f"{current_year - 2}1231",
        f"{current_year - 2}0930",
    ]

    top10_frames = []
    for period in periods:
        df = _fetch_top10_holders_for_period(pro, period=period)
        if df is not None and not df.empty:
            top10_frames.append(df)

    if not top10_frames:
        print("[Tushare-OWNS] 未取到 top10_holders 数据，跳过增强。")
        return 0, 0

    top10_df = pd.concat(top10_frames, ignore_index=True)
    top10_df = top10_df.drop_duplicates(subset=["ts_code", "holder_name", "end_date"], keep="first")

    print(f"[Tushare-OWNS] 合并 {len(top10_frames)} 个期末，返回 {top10_df.shape}")

    added = 0
    controller_hits = 0

    for _, row in top10_df.iterrows():
        dst_code = str(row.get("ts_code", "")).split(".")[0].zfill(6)
        dst_node = code_to_node.get(dst_code)
        if not dst_node:
            continue

        holder_name = _normalize_name(row.get("holder_name", ""))
        if not holder_name:
            continue

        holder_key = _entity_key(holder_name)
        src_candidates = alias_to_nodes.get(holder_key, set())
        if not src_candidates:
            continue

        hold_ratio = _safe_float(row.get("hold_ratio"))
        hold_amount = _safe_float(row.get("hold_amount"))

        if hold_ratio is not None and hold_ratio >= 20:
            controllers_by_company.setdefault(dst_node, set()).add(holder_name)
            controller_hits += 1

        for src_node in src_candidates:
            if src_node == dst_node:
                continue

            if graph.has_edge(src_node, dst_node):
                old = graph[src_node][dst_node]
                if str(old.get("relation", "")) != "OWNS_SHARES":
                    continue

                old_ratio = _safe_float(old.get("share_ratio"))
                if hold_ratio is not None and (old_ratio is None or hold_ratio > old_ratio):
                    old["share_ratio"] = hold_ratio
                old_amount = _safe_float(old.get("share_amount"))
                if hold_amount is not None and (old_amount is None or hold_amount > old_amount):
                    old["share_amount"] = hold_amount
                old["source"] = "stock_hold_control_cninfo+tushare.top10_holders"
                continue

            graph.add_edge(
                src_node,
                dst_node,
                relation="OWNS_SHARES",
                share_ratio=hold_ratio,
                share_amount=hold_amount,
                control_type="TOP10_HOLDER",
                report_date=str(row.get("end_date", "")).strip(),
                source="tushare.top10_holders",
            )
            added += 1

    print(f"[Tushare-OWNS] 新增 OWNS_SHARES 边: {added}，新增控制人命中: {controller_hits}")
    return added, controller_hits


def _recompute_same_controller_on_company_edges(graph, controllers_by_company: dict[str, set[str]]) -> int:
    patched = 0
    true_count = 0

    for u, v, attr in graph.edges(data=True):
        u_data = graph.nodes[u]
        v_data = graph.nodes[v]
        if u_data.get("node_type") != "company" or v_data.get("node_type") != "company":
            continue

        if u == v:
            # 自环担保边没有“与他方同一实控人”的语义。
            attr["same_controller"] = False
            attr["controller_overlap_count"] = 0
            patched += 1
            continue

        u_ctrl = controllers_by_company.get(u, set())
        v_ctrl = controllers_by_company.get(v, set())
        overlap = u_ctrl & v_ctrl

        same = len(overlap) > 0
        attr["same_controller"] = same
        attr["controller_overlap_count"] = len(overlap)
        patched += 1
        if same:
            true_count += 1

    print(f"[Step 4] 已给 {patched} 条公司间边补充 same_controller，其中 True: {true_count}")
    return patched


def run(input_path: str, output_path: str) -> None:
    graph = load_graph(input_path)
    pro = _get_tushare_pro()

    # 1) ST 标签
    graph, _ = patch_st_labels(graph)
    if pro is not None:
        _patch_st_labels_with_tushare(graph, pro)

    # 2) 股权关系边
    graph, _, controllers_by_company = patch_owns_shares_edges(graph)
    if pro is not None:
        _patch_owns_with_tushare_top10(graph, pro, controllers_by_company)

    # 3) 担保关系边（近两年窗口）
    today = date.today().strftime("%Y%m%d")
    start = f"{date.today().year - 2}0101"
    graph, _ = patch_guarantee_edges(graph, start_date=start, end_date=today)

    # 4) same_controller
    _recompute_same_controller_on_company_edges(graph, controllers_by_company)

    print_stats(graph)
    save_graph(graph, output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="四步补图独立入口")
    parser.add_argument("--input", default="data/base_graph.json", help="输入图路径")
    parser.add_argument("--output", default="data/base_graph_enriched.json", help="输出图路径")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.input, args.output)
