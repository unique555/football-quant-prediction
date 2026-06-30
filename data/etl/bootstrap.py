"""
ETL — 数据引导/初始化脚本
用于首次导入历史数据
→ 待实现
"""
import argparse
import logging

logger = logging.getLogger(__name__)


def bootstrap_league(league_code: str):
    """初始化单个联赛的全部数据 → 待实现"""
    logger.info(f"Bootstrapping league: {league_code}")
    raise NotImplementedError


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="足球数据初始化")
    parser.add_argument("--league", type=str, required=True, help="联赛代码 (e.g. epl, laliga)")
    args = parser.parse_args()
    bootstrap_league(args.league)
