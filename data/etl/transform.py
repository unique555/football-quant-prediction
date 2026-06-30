"""
ETL — 数据清洗与转换
→ 待实现
"""
import pandas as pd


def clean_match_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    """清洗比赛数据：去重、缺失值处理、格式标准化 → 待实现"""
    raise NotImplementedError


def normalize_team_names(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """球队名称标准化 → 待实现"""
    raise NotImplementedError


def merge_odds_with_matches(matches_df: pd.DataFrame, odds_df: pd.DataFrame) -> pd.DataFrame:
    """赔率与比赛数据合并 → 待实现"""
    raise NotImplementedError
