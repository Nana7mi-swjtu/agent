"""
按优先级补图：
1) ST 标签：给公司节点补充 is_st
2) 股权关系：新增 OWNS_SHARES 边
3) 担保关系：新增 GUARANTEES 边（基于担保统计）
4) 实控人字段：给公司间边新增 same_controller

使用说明：
- 默认读取 data/base_graph.json，补充后覆盖保存到同路径。
- 每一步都会先打印接口连通与列信息，再执行写图。
"""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from datetime import date
from typing import Iterable

import akshare as ak
import networkx as nx
import pandas as pd
from networkx.readwrite import json_graph
from requests.exceptions import RequestException


os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"


@contextmanager
def _disable_proxy_temporarily():
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY", "no_proxy"]
    backup = {k: os.environ.get(k) for k in proxy_keys}
    try:
        for key in proxy_keys:
            os.environ.pop(key, None)
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        yield
    finally:
        for key, value in backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _ak_call_with_proxy_fallback(func, *args, retries: int = 3, **kwargs):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except RequestException as e:
            last_error = e
            print(f"请求失败（第 {attempt}/{retries} 次），尝试直连: {e}")
            try:
                with _disable_proxy_temporarily():
                    return func(*args, **kwargs)
            except RequestException as e2:
                last_error = e2
                if attempt < retries:
                    wait_seconds = min(2 * attempt, 6)
                    print(f"直连仍失败，{wait_seconds}s 后重试...")
                    time.sleep(wait_seconds)

    if last_error is not None:
        raise last_error
    raise RuntimeError("未知网络错误：AkShare 调用失败")


def _pick_first(columns: Iterable[str], candidates: list[str]) -> str | None:
    cols = set(columns)
    for c in candidates:
        if c in cols:
            return c
    return None


def _safe_float(val) -> float | None:
    if val is None:
        return None
    text = str(val).strip().replace(",", "")
    if text in {"", "--", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _split_names(raw: str) -> list[str]:
    if not isinstance(raw, str):
        return []
    pieces = re.split(r"[;；,，、\n\r]+", raw)
    names = [p.strip() for p in pieces if p and p.strip()]
    return names


def _normalize_name(name: str) -> str:
    text = re.sub(r"\s+", "", str(name or "")).strip()
    text = text.replace("（", "(").replace("）", ")")
    return text


def load_graph(path: str = "data/base_graph.json") -> nx.DiGraph:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    g = json_graph.node_link_graph(data, directed=True)
    print(f"加载图：{g.number_of_nodes()} 节点，{g.number_of_edges()} 边")
    return g


def save_graph(g: nx.DiGraph, path: str = "data/base_graph.json"):
    data = json_graph.node_link_data(g)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"图已保存到 {path}")


def build_company_maps(g: nx.DiGraph):
    code_to_node = {}
    name_to_nodes = {}
    for node, data in g.nodes(data=True):
        if data.get("node_type") != "company":
            continue

        ts_code = str(data.get("ts_code", "")).split(".")[0].zfill(6)
        if ts_code:
            code_to_node[ts_code] = node

        norm_name = _normalize_name(data.get("name", ""))
        if norm_name:
            name_to_nodes.setdefault(norm_name, set()).add(node)

    return code_to_node, name_to_nodes


def fetch_st_codes() -> tuple[set[str], str]:
    print("[Step 1] 测试 ST 接口: ak.stock_zh_a_st_em")
    st_codes: set[str] = set()

    try:
        st_df = _ak_call_with_proxy_fallback(ak.stock_zh_a_st_em)
        code_col = _pick_first(st_df.columns, ["代码", "证券代码", "code"])
        print(f"  连通成功，返回 {st_df.shape}，列: {list(st_df.columns)}")
        if code_col is None:
            raise ValueError("ST 接口缺少代码列")

        st_codes = set(st_df[code_col].dropna().astype(str).str.zfill(6).tolist())
        return st_codes, "stock_zh_a_st_em"
    except Exception as e:
        print(f"  ST 接口不可用，回退到 ak.stock_zh_a_spot_em: {e}")

    try:
        spot_df = _ak_call_with_proxy_fallback(ak.stock_zh_a_spot_em)
        code_col = _pick_first(spot_df.columns, ["代码", "证券代码", "code"])
        name_col = _pick_first(spot_df.columns, ["名称", "证券简称", "name"])
        print(f"  回退连通成功，返回 {spot_df.shape}，列: {list(spot_df.columns)}")

        if code_col is None or name_col is None:
            raise ValueError("stock_zh_a_spot_em 缺少代码或名称列")

        name_series = spot_df[name_col].fillna("").astype(str).str.upper()
        mask = name_series.str.contains(r"(^\*?ST)|S\*ST", regex=True)
        st_codes = set(spot_df.loc[mask, code_col].astype(str).str.zfill(6).tolist())
        return st_codes, "stock_zh_a_spot_em_fallback"
    except Exception as e:
        print(f"  二级回退也失败，使用图内公司简称识别 ST: {e}")
        return set(), "graph_name_fallback"


def patch_st_labels(g: nx.DiGraph) -> tuple[nx.DiGraph, int]:
    st_codes, source = fetch_st_codes()
    patched = 0

    for _, data in g.nodes(data=True):
        if data.get("node_type") != "company":
            continue
        ts_code = str(data.get("ts_code", "")).split(".")[0].zfill(6)
        if source == "graph_name_fallback":
            name_upper = str(data.get("name", "")).upper().strip()
            is_st = bool(re.search(r"(^\*?ST)|S\*ST", name_upper))
        else:
            is_st = ts_code in st_codes
        data["is_st"] = is_st
        data["is_st_source"] = source
        patched += 1

    st_count = sum(1 for _, d in g.nodes(data=True) if d.get("node_type") == "company" and d.get("is_st") is True)
    print(f"[Step 1] 已更新 {patched} 家公司 is_st，命中 ST: {st_count}")
    return g, st_count


def fetch_control_df() -> pd.DataFrame:
    print("[Step 2] 测试股权接口: ak.stock_hold_control_cninfo(symbol='全部')")
    control_df = _ak_call_with_proxy_fallback(ak.stock_hold_control_cninfo, symbol="全部")
    print(f"  连通成功，返回 {control_df.shape}，列: {list(control_df.columns)}")
    return control_df


def patch_owns_shares_edges(g: nx.DiGraph) -> tuple[nx.DiGraph, int, dict[str, set[str]]]:
    control_df = fetch_control_df()
    code_to_node, name_to_nodes = build_company_maps(g)

    code_col = _pick_first(control_df.columns, ["证券代码", "代码"])
    direct_col = _pick_first(control_df.columns, ["直接控制人名称"])
    real_col = _pick_first(control_df.columns, ["实际控制人名称"])
    ratio_col = _pick_first(control_df.columns, ["控股比例"])
    amount_col = _pick_first(control_df.columns, ["控股数量"])
    ctype_col = _pick_first(control_df.columns, ["控制类型"])
    date_col = _pick_first(control_df.columns, ["变动日期"])

    if code_col is None or direct_col is None:
        raise ValueError("股权接口缺少关键列：证券代码/直接控制人名称")

    controllers_by_company: dict[str, set[str]] = {}
    added = 0

    for _, row in control_df.iterrows():
        dst_code = str(row.get(code_col, "")).strip().zfill(6)
        dst_node = code_to_node.get(dst_code)
        if not dst_node:
            continue

        real_names = {_normalize_name(x) for x in _split_names(str(row.get(real_col, "")))}
        real_names = {x for x in real_names if x}
        controllers_by_company.setdefault(dst_node, set()).update(real_names)

        direct_names = [_normalize_name(x) for x in _split_names(str(row.get(direct_col, "")))]
        direct_names = [x for x in direct_names if x]
        if not direct_names:
            continue

        for direct_name in direct_names:
            src_candidates = name_to_nodes.get(direct_name, set())
            if not src_candidates:
                continue

            for src_node in src_candidates:
                if src_node == dst_node:
                    continue
                if g.has_edge(src_node, dst_node):
                    # DiGraph 不支持同一对节点多条边，保留原关系，避免覆盖。
                    continue

                g.add_edge(
                    src_node,
                    dst_node,
                    relation="OWNS_SHARES",
                    share_ratio=_safe_float(row.get(ratio_col)) if ratio_col else None,
                    share_amount=_safe_float(row.get(amount_col)) if amount_col else None,
                    control_type=str(row.get(ctype_col, "")).strip() if ctype_col else None,
                    report_date=str(row.get(date_col, "")).strip() if date_col else None,
                    source="stock_hold_control_cninfo",
                )
                added += 1

    print(f"[Step 2] 新增 OWNS_SHARES 边: {added}")
    return g, added, controllers_by_company


def fetch_guarantee_df(start_date: str, end_date: str) -> pd.DataFrame:
    print(
        "[Step 3] 测试担保接口: "
        f"ak.stock_cg_guarantee_cninfo(symbol='全部', start_date='{start_date}', end_date='{end_date}')"
    )
    guarantee_df = _ak_call_with_proxy_fallback(
        ak.stock_cg_guarantee_cninfo,
        symbol="全部",
        start_date=start_date,
        end_date=end_date,
    )
    print(f"  连通成功，返回 {guarantee_df.shape}，列: {list(guarantee_df.columns)}")
    return guarantee_df


def patch_guarantee_edges(g: nx.DiGraph, start_date: str, end_date: str) -> tuple[nx.DiGraph, int]:
    guarantee_df = fetch_guarantee_df(start_date=start_date, end_date=end_date)
    code_to_node, _ = build_company_maps(g)

    code_col = _pick_first(guarantee_df.columns, ["证券代码", "代码"])
    count_col = _pick_first(guarantee_df.columns, ["担保笔数"])
    amount_col = _pick_first(guarantee_df.columns, ["担保金额"])
    ratio_col = _pick_first(guarantee_df.columns, ["担保金融占净资产比例"])
    period_col = _pick_first(guarantee_df.columns, ["公告统计区间"])

    if code_col is None:
        raise ValueError("担保接口缺少代码列")

    added = 0
    for _, row in guarantee_df.iterrows():
        code = str(row.get(code_col, "")).strip().zfill(6)
        node = code_to_node.get(code)
        if not node:
            continue

        # 当前 AKShare 对外担保接口是公司级汇总，无被担保方字段；用自环保留担保语义。
        if g.has_edge(node, node):
            continue

        g.add_edge(
            node,
            node,
            relation="GUARANTEES",
            guarantee_count=_safe_float(row.get(count_col)) if count_col else None,
            guarantee_amount=_safe_float(row.get(amount_col)) if amount_col else None,
            guarantee_ratio=_safe_float(row.get(ratio_col)) if ratio_col else None,
            guarantee_period=str(row.get(period_col, "")).strip() if period_col else None,
            source="stock_cg_guarantee_cninfo",
        )
        added += 1

    print(f"[Step 3] 新增 GUARANTEES 边: {added}")
    return g, added


def patch_same_controller_on_edges(g: nx.DiGraph, controllers_by_company: dict[str, set[str]]) -> tuple[nx.DiGraph, int]:
    patched = 0
    for u, v, attr in g.edges(data=True):
        u_data = g.nodes[u]
        v_data = g.nodes[v]
        if u_data.get("node_type") != "company" or v_data.get("node_type") != "company":
            continue

        u_ctrl = controllers_by_company.get(u, set())
        v_ctrl = controllers_by_company.get(v, set())

        if u == v:
            same = True
            overlap_count = len(u_ctrl)
        else:
            overlap = u_ctrl & v_ctrl
            same = len(overlap) > 0
            overlap_count = len(overlap)

        attr["same_controller"] = same
        attr["controller_overlap_count"] = overlap_count
        patched += 1

    print(f"[Step 4] 已给 {patched} 条公司间边补充 same_controller")
    return g, patched


def print_stats(g: nx.DiGraph):
    companies = [n for n, d in g.nodes(data=True) if d.get("node_type") == "company"]
    st_count = sum(1 for n in companies if g.nodes[n].get("is_st") is True)

    owns_edges = 0
    guarantee_edges = 0
    same_true = 0

    for _, _, attr in g.edges(data=True):
        rel = str(attr.get("relation", ""))
        if rel == "OWNS_SHARES":
            owns_edges += 1
        elif rel == "GUARANTEES":
            guarantee_edges += 1

        if attr.get("same_controller") is True:
            same_true += 1

    print("\n=== 补图结果统计 ===")
    print(f"公司节点数: {len(companies)}")
    print(f"ST 公司数: {st_count}")
    print(f"OWNS_SHARES 边数: {owns_edges}")
    print(f"GUARANTEES 边数: {guarantee_edges}")
    print(f"same_controller=True 的公司间边数: {same_true}")


def main():
    g = load_graph("data/base_graph.json")

    # 1) ST 标签
    g, _ = patch_st_labels(g)

    # 2) 股权关系边
    g, _, controllers_by_company = patch_owns_shares_edges(g)

    # 3) 担保关系边（近两年窗口）
    today = date.today().strftime("%Y%m%d")
    start = f"{date.today().year - 2}0101"
    g, _ = patch_guarantee_edges(g, start_date=start, end_date=today)

    # 4) same_controller
    g, _ = patch_same_controller_on_edges(g, controllers_by_company)

    print_stats(g)
    save_graph(g, "data/base_graph.json")


if __name__ == "__main__":
    main()

