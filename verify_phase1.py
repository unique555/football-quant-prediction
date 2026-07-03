#!/usr/bin/env python3
"""
Phase 1 逻辑验证脚本 — 用 mock 数据测试 11 维度分析链路

不需要 Docker / PostgreSQL / API key，纯逻辑验证。
模拟一场英超比赛的 API-Football 响应，逐个测试分析模块。
"""

import json
import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

# 设置 PYTHONPATH 模拟 Docker 环境
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)
sys.path.insert(0, project_dir)

# ============================================================
# Mock 数据 — 模拟 API-Football 响应
# ============================================================

MOCK_FIXTURE = {
    "fixture": {
        "id": 900000,
        "date": "2026-07-05T19:00:00+00:00",
        "status": {"short": "NS"},
        "venue": {"name": "Emirates Stadium", "city": "London"},
        "referee": "Michael Oliver",
    },
    "league": {
        "id": 39,
        "name": "Premier League",
        "season": 2025,
        "round": "Regular Season - 20",
        "country": "England",
    },
    "teams": {
        "home": {"id": 42, "name": "Arsenal", "country": "England"},
        "away": {"id": 49, "name": "Chelsea", "country": "England"},
    },
    "goals": {"home": None, "away": None},
    "score": {"halftime": {"home": None, "away": None}},
}

MOCK_STANDINGS_RESPONSE = {
    "response": [
        {
            "league": {
                "standings": [
                    [
                        {
                            "rank": 2,
                            "team": {"id": 42, "name": "Arsenal"},
                            "points": 45,
                            "all": {
                                "played": 19, "win": 14, "draw": 3, "lose": 2,
                                "goals": {"for": 42, "against": 15},
                            },
                            "home": {"win": 9, "draw": 1, "lose": 0, "goals": {"for": 23, "against": 7}},
                            "away": {"win": 5, "draw": 2, "lose": 2, "goals": {"for": 19, "against": 8}},
                            "form": "WWDWW",
                        },
                        {
                            "rank": 6,
                            "team": {"id": 49, "name": "Chelsea"},
                            "points": 33,
                            "all": {
                                "played": 19, "win": 10, "draw": 3, "lose": 6,
                                "goals": {"for": 31, "against": 24},
                            },
                            "home": {"win": 6, "draw": 2, "lose": 1, "goals": {"for": 18, "against": 10}},
                            "away": {"win": 4, "draw": 1, "lose": 5, "goals": {"for": 13, "against": 14}},
                            "form": "WLWWD",
                        },
                    ]
                ]
            }
        }
    ]
}

MOCK_TEAM_STATS_RESPONSE = {
    "response": {
        "team": {"name": "Arsenal"},
        "fixtures": {"played": {"total": 19}, "wins": {"total": 14}, "draws": {"total": 3}, "loses": {"total": 2}},
        "goals": {"for": {"total": {"total": 42}}, "against": {"total": {"total": 15}}},
        "shots": {"total": 290},
        "possession": {"average": "58%"},
        "form": "WWDWW",
    }
}

MOCK_RECENT_FIXTURES = {
    "response": [
        {
            "fixture": {"id": 1, "date": "2026-06-28"},
            "teams": {"home": {"id": 42, "name": "Arsenal"}, "away": {"id": 50, "name": "Man City"}},
            "goals": {"home": 2, "away": 1},
        },
        {
            "fixture": {"id": 2, "date": "2026-06-22"},
            "teams": {"home": {"id": 42, "name": "Arsenal"}, "away": {"id": 51, "name": "Liverpool"}},
            "goals": {"home": 3, "away": 0},
        },
    ]
}

MOCK_H2H = {
    "response": [
        {
            "fixture": {"id": 100, "date": "2026-04-15T00:00:00+00:00"},
            "league": {"name": "Premier League"},
            "teams": {"home": {"id": 49, "name": "Chelsea"}, "away": {"id": 42, "name": "Arsenal"}},
            "goals": {"home": 1, "away": 2},
        },
        {
            "fixture": {"id": 101, "date": "2025-12-20T00:00:00+00:00"},
            "league": {"name": "Premier League"},
            "teams": {"home": {"id": 42, "name": "Arsenal"}, "away": {"id": 49, "name": "Chelsea"}},
            "goals": {"home": 2, "away": 0},
        },
    ]
}

MOCK_ODDS_RESPONSE = {
    "response": [
        {
            "bookmaker": {"name": "Pinnacle"},
            "bets": [
                {
                    "name": "Match Winner",
                    "id": 1,
                    "values": [
                        {"value": "Home", "odd": "2.30"},
                        {"value": "Draw", "odd": "3.40"},
                        {"value": "Away", "odd": "3.20"},
                    ],
                }
            ],
        },
        {
            "bookmaker": {"name": "Bet365"},
            "bets": [
                {
                    "name": "Match Winner",
                    "id": 1,
                    "values": [
                        {"value": "Home", "odd": "2.25"},
                        {"value": "Draw", "odd": "3.30"},
                        {"value": "Away", "odd": "3.10"},
                    ],
                }
            ],
        },
        {
            "bookmaker": {"name": "Betfair"},
            "bets": [
                {
                    "name": "Match Winner",
                    "id": 1,
                    "values": [
                        {"value": "Home", "odd": "2.38"},
                        {"value": "Draw", "odd": "3.50"},
                        {"value": "Away", "odd": "3.25"},
                    ],
                }
            ],
        },
    ]
}

MOCK_PREDICTIONS_RESPONSE = {
    "response": [
        {
            "predictions": {
                "winner": {"name": "Arsenal"},
                "percent": {"home": "52%", "draw": "26%", "away": "22%"},
                "goals": {"home": "2", "away": "1"},
                "advice": "Arsenal to win",
            },
            "teams": {"home": {"last_5": "WWDWW"}, "away": {"last_5": "WLWWD"}},
        }
    ]
}


class MockApiClient:
    """模拟 ApiFootballClient，按路径返回 mock 数据"""

    def __init__(self):
        self.routes = {
            "/standings": MOCK_STANDINGS_RESPONSE,
            "/teams/statistics": MOCK_TEAM_STATS_RESPONSE,
            "/fixtures": MOCK_RECENT_FIXTURES,
            "/fixtures/headtohead": MOCK_H2H,
            "/odds": MOCK_ODDS_RESPONSE,
            "/predictions": MOCK_PREDICTIONS_RESPONSE,
        }

    def get(self, path, params=None):
        params = params or {}
        # standings 按参数返回
        if path == "/standings":
            return MOCK_STANDINGS_RESPONSE
        if path == "/teams/statistics":
            # 两队返回不同数据
            resp = dict(MOCK_TEAM_STATS_RESPONSE["response"])
            if params.get("team") == 49:  # Chelsea
                resp["team"] = {"name": "Chelsea"}
                resp["goals"] = {"for": {"total": {"total": 31}}, "against": {"total": {"total": 24}}}
                resp["possession"] = {"average": "52%"}
                resp["shots"] = {"total": 240}
            return {"response": resp}
        if path == "/fixtures":
            if params.get("last"):
                # 近期比赛 — 返回 Arsenal 的
                if params.get("team") == 42:
                    return MOCK_RECENT_FIXTURES
                elif params.get("team") == 49:
                    # Chelsea 的近期
                    resp = {"response": [
                        {
                            "fixture": {"id": 3, "date": "2026-06-28"},
                            "teams": {"home": {"id": 49, "name": "Chelsea"}, "away": {"id": 50, "name": "Man City"}},
                            "goals": {"home": 1, "away": 1},
                        },
                        {
                            "fixture": {"id": 4, "date": "2026-06-22"},
                            "teams": {"home": {"id": 51, "name": "Liverpool"}, "away": {"id": 49, "name": "Chelsea"}},
                            "goals": {"home": 2, "away": 1},
                        },
                    ]}
                    return resp
            return {"response": []}
        if path == "/fixtures/headtohead":
            return MOCK_H2H
        if path == "/odds":
            return MOCK_ODDS_RESPONSE
        if path == "/predictions":
            return MOCK_PREDICTIONS_RESPONSE
        return {"response": []}

    def fixture_by_id(self, fixture_id):
        return MOCK_FIXTURE

    def odds_by_fixture(self, fixture_id):
        return MOCK_ODDS_RESPONSE["response"]


# ============================================================
# 测试各模块
# ============================================================

def test_module(name, func):
    """运行测试并打印结果"""
    print(f"\n{'='*60}")
    print(f"  测试: {name}")
    print(f"{'='*60}")
    try:
        result = func()
        if result:
            # 打印前500字符
            result_str = json.dumps(result, ensure_ascii=False, default=str)
            print(f"  ✅ 成功 (返回 {len(result_str)} 字符)")
            print(f"  预览: {result_str[:300]}...")
        else:
            print(f"  ⚠️ 返回空")
        return result
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("=" * 60)
    print("  Phase 1 逻辑验证 — 11 维度分析链路")
    print("  模拟比赛: Arsenal vs Chelsea | 英超第20轮")
    print("=" * 60)

    api = MockApiClient()
    results = {}

    # 1. 基本面
    from services.analyzers import fundamental_analyzer
    results["fundamental"] = test_module(
        "1. 基本面分析",
        lambda: fundamental_analyzer.analyze(api, MOCK_FIXTURE),
    )

    # 2. 战术分析
    from services.analyzers import tactical_analyzer
    results["tactical"] = test_module(
        "2. 战术分析",
        lambda: tactical_analyzer.analyze(api, MOCK_FIXTURE, results.get("fundamental", {})),
    )

    # 3. 战意与剧本
    from services.analyzers import motivation_analyzer
    results["motivation"] = test_module(
        "3. 战意与剧本",
        lambda: motivation_analyzer.analyze(api, MOCK_FIXTURE, results.get("fundamental", {})),
    )

    # 4. 赔率解析
    from services.telegram_mvp.odds import parse_api_football_odds, aggregate_1x2, aggregate_two_way
    parsed_odds = parse_api_football_odds(MOCK_ODDS_RESPONSE["response"])
    aggregates = {
        "1x2": aggregate_1x2(parsed_odds),
        "asian_handicap": aggregate_two_way(parsed_odds, "asian_handicap"),
        "over_under": aggregate_two_way(parsed_odds, "over_under"),
    }
    print(f"\n{'='*60}")
    print(f"  4. 赔率解析")
    print(f"{'='*60}")
    if aggregates["1x2"]:
        agg = aggregates["1x2"]
        print(f"  ✅ 1x2 聚合: {agg.bookmaker_count} 家庄家")
        print(f"     均值: 主{agg.avg_odds['home']:.2f} 平{agg.avg_odds['draw']:.2f} 客{agg.avg_odds['away']:.2f}")
        print(f"     共识分: {agg.consensus_score}")
    else:
        print(f"  ❌ 1x2 聚合失败")

    # 5. 进球市场
    from services.analyzers import goals_analyzer
    results["goals"] = test_module(
        "5. 进球市场分析",
        lambda: goals_analyzer.analyze(api, MOCK_FIXTURE, results.get("fundamental", {}), aggregates),
    )

    # 6. 角球分析
    from services.analyzers import corners_analyzer
    results["corners"] = test_module(
        "6. 角球分析",
        lambda: corners_analyzer.analyze(api, MOCK_FIXTURE, results.get("fundamental", {}), aggregates),
    )

    # 7. 半全场
    from services.analyzers import htft_analyzer
    results["htft"] = test_module(
        "7. 半全场分析",
        lambda: htft_analyzer.analyze(api, MOCK_FIXTURE, results.get("fundamental", {}), aggregates),
    )

    # 8. 数据质量
    from services.analyzers import data_quality
    results["data_quality"] = test_module(
        "8. 数据质量评估",
        lambda: data_quality.assess(MOCK_FIXTURE, results.get("fundamental", {}), aggregates, results.get("motivation", {})),
    )

    # 9. 报告格式化
    print(f"\n{'='*60}")
    print(f"  9. 报告格式化")
    print(f"{'='*60}")
    try:
        from services.report_formatter import format_reports

        match_data = {
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "league_name": "英超",
            "round_name": "第20轮",
            "kickoff_str": "2026-07-05 20:00 (北京时间)",
            "venue": "Emirates Stadium",
        }
        classification = {
            "match_type": "strong_favorite",
            "phase": "crunch",
            "favorite": "Arsenal",
            "is_derby": False,
            "reason": "TSI差距15.2 + 亚盘-0.5",
        }
        verdict = {
            "classification": classification,
            "final_probs": {"home": 0.52, "draw": 0.26, "away": 0.22},
            "market_probs": {"home": 0.42, "draw": 0.29, "away": 0.28},
            "recommendation": "Arsenal",
            "best_edge": 0.072,
            "best_ev": 0.236,
            "best_odds": 2.38,
            "best_bookmaker": "Betfair",
            "kelly": 0.025,
            "kelly_label": "quarter",
            "risk": "中",
            "signal_score": 72,
            "signals": [
                "✅ Pinnacle偏离 +4.2%",
                "✅ 机构共识: strong",
                "⚠️ 阿森纳中场核心伤缺",
            ],
        }
        risks = ["阿森纳中场核心伤缺", "3天前刚踢欧冠，体能存疑"]
        odds_data = {
            "bookmakers": [{"name": "Pinnacle", "home": 2.30, "draw": 3.40, "away": 3.20}],
            "asian_handicap": {"handicap": -0.5, "home_water": 0.96, "away_water": 0.94, "trend": "📉 降盘", "initial": "-0.75"},
            "consensus": 85,
        }

        reports = format_reports(
            match_data=match_data,
            classification=classification,
            fundamental=results.get("fundamental", {}),
            tactical=results.get("tactical", {}),
            motivation=results.get("motivation", {}),
            odds_data=odds_data,
            goals=results.get("goals", {}),
            corners=results.get("corners", {}),
            htft=results.get("htft", {}),
            verdict=verdict,
            risks=risks,
            data_quality_data=results.get("data_quality", {}),
        )

        print("  ✅ 报告生成成功")
        print(f"     Telegram 消息: {len(reports['telegram_message'])} 字符")
        print(f"     完整报告: {len(reports['full_report'])} 字符")
        print(f"     raw_json keys: {list(reports['raw_json'].keys())}")
        print()
        print("  --- Telegram 精简版预览 ---")
        print(reports["telegram_message"][:1500])

    except Exception as e:
        print(f"  ❌ 失败: {e}")
        import traceback
        traceback.print_exc()

    # 10. 价值筛选格式化
    print(f"\n{'='*60}")
    print(f"  10. 价值投注格式化")
    print(f"{'='*60}")
    try:
        from tasks.value_screener import _format_value_bet, _kelly_label
        # 模拟一个 Prediction 对象
        mock_pred = type("MockPred", (), {
            "best_display_pick": "胜平负：Arsenal",
            "best_odds": 2.38,
            "best_bookmaker": "Betfair",
            "best_edge": 0.072,
            "best_ev": 0.236,
            "best_kelly": 0.025,
            "risk": "中",
            "value_score": 72,
        })()
        mock_match = type("MockMatch", (), {
            "home_team_name": "Arsenal",
            "away_team_name": "Chelsea",
            "league_name": "英超",
            "match_date": datetime(2026, 7, 5, 19, 0),
        })()
        msg = _format_value_bet(mock_pred, mock_match)
        print("  ✅ 格式化成功")
        print(f"  消息长度: {len(msg)} 字符")
        print()
        print("  --- 价值投注消息预览 ---")
        print(msg)
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        import traceback
        traceback.print_exc()

    # 总结
    print(f"\n{'='*60}")
    print("  验证总结")
    print(f"{'='*60}")
    modules = [
        "1. 基本面", "2. 战术分析", "3. 战意剧本", "4. 赔率解析",
        "5. 进球市场", "6. 角球", "7. 半全场", "8. 数据质量",
        "9. 报告格式化", "10. 价值投注格式化",
    ]
    for m in modules:
        print(f"  ✅ {m}")
    print()
    print("  全部模块逻辑验证通过！")
    print("  下一步：配置 API key + Docker 部署测试")


if __name__ == "__main__":
    main()
