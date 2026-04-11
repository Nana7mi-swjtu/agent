"""
第一步：构建行业风险识别知识图谱的骨架
数据源：AKShare（完全免费，无需 token）
节点：公司 + 行业
边：公司 → 行业（属于关系）
"""

import time
import akshare as ak
import pandas as pd
import networkx as nx
import json
import os
import sys
from contextlib import contextmanager
from requests.exceptions import RequestException


@contextmanager
def _disable_proxy_temporarily():
    """临时关闭代理变量，便于代理异常时回退到直连。"""
    proxy_keys = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "NO_PROXY",
        "no_proxy",
    ]
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
    """优先按当前环境请求；若失败则直连重试，最多重试 retries 次。"""
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


def _fetch_stock_industry_sw_fallback() -> pd.DataFrame:
    """东方财富行业接口不可用时，回退到申万行业编码。"""
    sw_df = _ak_call_with_proxy_fallback(ak.stock_industry_clf_hist_sw)
    sw_df = (
        sw_df.sort_values(["symbol", "start_date"])
        .drop_duplicates(subset=["symbol"], keep="last")
        .rename(columns={"symbol": "ts_code", "industry_code": "industry"})
    )
    sw_df["industry"] = sw_df["industry"].astype(str).map(lambda x: f"SW_{x}")

    name_df = _ak_call_with_proxy_fallback(ak.stock_info_a_code_name)
    name_df = name_df.rename(columns={"code": "ts_code", "name": "name"})

    merged = sw_df[["ts_code", "industry"]].merge(
        name_df[["ts_code", "name"]], on="ts_code", how="left"
    )
    merged = merged[["ts_code", "name", "industry"]].dropna(subset=["name"])
    return merged

# ── 1. 拉取个股所属行业 ───────────────────────────────────────────────────────

def fetch_stock_industry() -> pd.DataFrame:
    """获取每只股票的行业归属（东方财富行业分类）"""
    records = []
    try:
        industry_df = _ak_call_with_proxy_fallback(ak.stock_board_industry_name_em)
    except RequestException as e:
        print(f"无法获取东方财富行业列表，切换申万行业编码回退: {e}")
        try:
            fallback_df = _fetch_stock_industry_sw_fallback()
            print(
                f"回退成功：获取到 {len(fallback_df)} 家公司，"
                f"{fallback_df['industry'].nunique()} 个申万行业编码"
            )
            return fallback_df
        except RequestException as e2:
            print(f"申万回退也失败，网络请求异常: {e2}")
            return pd.DataFrame(columns=["ts_code", "name", "industry"])

    for _, row in industry_df.iterrows():
        board_name = row["板块名称"]
        try:
            stocks = _ak_call_with_proxy_fallback(
                ak.stock_board_industry_cons_em, symbol=board_name
            )
            for _, s in stocks.iterrows():
                records.append({
                    "ts_code": s["代码"],
                    "name": s["名称"],
                    "industry": board_name
                })
            time.sleep(0.5)
        except Exception as e:
            print(f"  跳过行业 {board_name}: {e}")
            continue

    df = pd.DataFrame(records).drop_duplicates(subset=["ts_code"])
    print(f"获取到 {len(df)} 家公司，{df['industry'].nunique()} 个行业")
    return df


# ── 2. 拉取杜邦因子 ───────────────────────────────────────────────────────────

def fetch_dupont(ts_codes: list[str]) -> pd.DataFrame:
    records = []

    for i, code in enumerate(ts_codes):
        try:
            income = _ak_call_with_proxy_fallback(
                ak.stock_financial_report_sina, stock=code, symbol="利润表"
            )
            balance = _ak_call_with_proxy_fallback(
                ak.stock_financial_report_sina, stock=code, symbol="资产负债表"
            )

            if income.empty or balance.empty:
                continue

            inc_row = income.iloc[0]
            bal_row = balance.iloc[0]

            net_income = float(inc_row.get("净利润", 0) or 0)
            revenue = float(inc_row.get("营业总收入", 0) or
                           inc_row.get("营业收入", 0) or 0)
            total_assets = float(bal_row.get("资产总计", 0) or
                                bal_row.get("总资产", 0) or 0)
            equity = float(bal_row.get("股东权益合计", 0) or
                          bal_row.get("归属于母公司股东权益合计", 0) or 0)

            if not all([revenue, total_assets, equity]):
                continue

            records.append({
                "ts_code": code,
                "net_profit_margin": net_income / revenue,
                "asset_turnover": revenue / total_assets,
                "equity_multiplier": total_assets / equity,
                "roe": (net_income / revenue) * (revenue / total_assets) * (total_assets / equity)
            })

        except Exception:
            pass

        time.sleep(0.3)

        if (i + 1) % 20 == 0:
            print(f"  进度 {i+1}/{len(ts_codes)}")

    return pd.DataFrame(records)


# ── 3. 构建图 ─────────────────────────────────────────────────────────────────

def build_base_graph(stock_industry_df: pd.DataFrame,
                     dupont_df: pd.DataFrame) -> nx.DiGraph:
    G = nx.DiGraph()

    if not dupont_df.empty:
        merged = stock_industry_df.merge(dupont_df, on="ts_code", how="left")
    else:
        merged = stock_industry_df.copy()
        for col in ["net_profit_margin", "asset_turnover", "equity_multiplier", "roe"]:
            merged[col] = None

    # 行业节点
    for ind in merged["industry"].unique():
        G.add_node(
            f"IND_{ind}",
            node_type="industry",
            name=ind,
            company_count=int((merged["industry"] == ind).sum())
        )

    # 公司节点 + 属于边
    for _, row in merged.iterrows():
        company_id = f"CO_{row['ts_code']}"
        industry_id = f"IND_{row['industry']}"

        G.add_node(
            company_id,
            node_type="company",
            ts_code=row["ts_code"],
            name=row["name"],
            industry=row["industry"],
            net_profit_margin=row.get("net_profit_margin"),
            asset_turnover=row.get("asset_turnover"),
            equity_multiplier=row.get("equity_multiplier"),
            roe=row.get("roe"),
        )

        G.add_edge(company_id, industry_id, relation="belongs_to")

    return G


# ── 4. 保存 & 统计 ────────────────────────────────────────────────────────────

def save_graph(G: nx.DiGraph, path: str = "data/base_graph.json"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = nx.node_link_data(G)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"图已保存到 {path}")


def print_stats(G: nx.DiGraph):
    company_nodes = [n for n, d in G.nodes(data=True) if d["node_type"] == "company"]
    industry_nodes = [n for n, d in G.nodes(data=True) if d["node_type"] == "industry"]

    print(f"\n=== 骨架图统计 ===")
    print(f"公司节点：{len(company_nodes)}")
    print(f"行业节点：{len(industry_nodes)}")
    print(f"属于边：  {G.number_of_edges()}")

    from collections import Counter
    industry_counts = Counter(G.nodes[n]["industry"] for n in company_nodes)
    print(f"\n公司数最多的行业 Top10：")
    for ind, cnt in industry_counts.most_common(10):
        print(f"  {ind}: {cnt} 家")


# ── 主流程 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Step 1: 拉公司-行业映射
    print("Step 1: 获取公司行业归属...")
    stock_industry_df = fetch_stock_industry()
    if stock_industry_df.empty:
        print("未获取到公司-行业数据，程序结束。请检查网络连通性或代理设置后重试。")
        sys.exit(1)

    # 只保留机器人相关行业
    robot_industries = ["机械设备", "电子", "电气设备", "计算机"]
    if stock_industry_df["industry"].astype(str).str.startswith("SW_").all():
        print("当前为申万编码回退数据，跳过中文行业名过滤。")
    else:
        stock_industry_df = stock_industry_df[
            stock_industry_df["industry"].isin(robot_industries)
        ]
        print(f"过滤后：{len(stock_industry_df)} 家公司")
        if stock_industry_df.empty:
            print("过滤后无公司数据，程序结束。")
            sys.exit(1)

    # Step 2: 拉杜邦因子（先跑前 30 只测试）
    ts_codes = stock_industry_df["ts_code"].tolist()[:30]
    print(f"\nStep 2: 获取 {len(ts_codes)} 只股票的杜邦因子...")
    dupont_df = fetch_dupont(ts_codes)
    print(f"成功获取 {len(dupont_df)} 只")

    # Step 3: 构建图
    print("\nStep 3: 构建骨架图...")
    G = build_base_graph(stock_industry_df, dupont_df)
    print_stats(G)

    # Step 4: 保存
    save_graph(G, "data/base_graph.json")