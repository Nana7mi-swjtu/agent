from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoboticsTaxonomyEntry:
    segment: str
    chain_position: str
    keywords: tuple[str, ...]


ROBOTICS_TAXONOMY: tuple[RoboticsTaxonomyEntry, ...] = (
    RoboticsTaxonomyEntry("人形机器人", "中游本体", ("人形机器人", "具身智能", "仿生机器人", "双足机器人")),
    RoboticsTaxonomyEntry("服务机器人", "下游应用", ("服务机器人", "商用服务机器人", "配送机器人", "接待机器人")),
    RoboticsTaxonomyEntry("扫地机器人", "下游应用", ("扫地机器人", "清洁机器人", "智能清洁", "家庭服务机器人")),
    RoboticsTaxonomyEntry("工业机器人", "中游本体", ("工业机器人", "智能制造", "自动化产线", "协作机器人")),
    RoboticsTaxonomyEntry("核心零部件", "上游零部件", ("减速器", "谐波减速器", "伺服电机", "控制器", "执行器", "丝杠", "轴承")),
    RoboticsTaxonomyEntry("感知与导航", "上游零部件", ("传感器", "激光雷达", "机器视觉", "视觉模组", "SLAM", "导航定位")),
    RoboticsTaxonomyEntry("智能仓储", "下游应用", ("智能仓储", "仓储机器人", "物流机器人", "AGV", "AMR")),
    RoboticsTaxonomyEntry("医疗康养机器人", "下游应用", ("医疗机器人", "康养机器人", "养老机器人", "康复机器人")),
    RoboticsTaxonomyEntry("教育机器人", "下游应用", ("教育机器人", "教学机器人", "科教机器人")),
)

GENERAL_ROBOTICS_KEYWORDS: tuple[str, ...] = (
    "机器人",
    "人形机器人",
    "服务机器人",
    "扫地机器人",
    "工业机器人",
    "智能制造",
    "具身智能",
)

KNOWN_ENTERPRISE_HINTS: dict[str, tuple[str, ...]] = {
    "石头科技": ("扫地机器人", "服务机器人", "智能清洁"),
    "科沃斯": ("扫地机器人", "服务机器人", "清洁机器人"),
    "优必选": ("人形机器人", "服务机器人", "具身智能"),
    "埃斯顿": ("工业机器人", "智能制造", "控制器"),
    "绿的谐波": ("减速器", "谐波减速器", "核心零部件"),
    "汇川技术": ("工业机器人", "伺服电机", "控制器"),
    "机器人": ("工业机器人", "智能制造", "系统集成"),
    "三花智控": ("执行器", "人形机器人", "核心零部件"),
    "拓普集团": ("执行器", "人形机器人", "核心零部件"),
    "鸣志电器": ("电机", "执行器", "核心零部件"),
}
