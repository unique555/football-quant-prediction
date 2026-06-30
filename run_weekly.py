#!/usr/bin/env python3
"""
周度复盘 & 自优化 — 汇总本周所有分析, 自动调优模型
用法: python3 run_weekly.py
输出: reports/weekly/YYYY-WW_review.md
"""
import os, sys, json, glob, re
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model.trainer import get_model

REPORTS_DIR = "/workspace/football-quant-prediction/reports"
HISTORY_DB = "/workspace/football-quant-prediction/data/football_data_co_uk.csv"


def get_week_dates() -> tuple:
    """计算本周一~周日"""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def collect_week_results(start: str, end: str) -> list:
    """收集本周所有复盘文件"""
    results = []
    current = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    
    while current <= end_dt:
        d = current.strftime("%Y-%m-%d")
        result_file = f"{REPORTS_DIR}/{d}_results.md"
        if os.path.exists(result_file):
            # 从 MD 解析指标
            with open(result_file) as f:
                content = f.read()
            
            acc_match = re.search(r'准确率\s*\|\s*([\d.]+)%', content)
            brier_match = re.search(r'Brier Score\s*\|\s*([\d.]+)', content)
            total_match = re.search(r'完赛场次\s*\|\s*(\d+)', content)
            
            results.append({
                "date": d,
                "accuracy": float(acc_match.group(1)) / 100 if acc_match else 0,
                "brier": float(brier_match.group(1)) if brier_match else 0,
                "total": int(total_match.group(1)) if total_match else 0,
            })
        current += timedelta(days=1)
    
    return results


def optimize_model():
    """基于最新赛季自动调优"""
    print("🔧 自动优化...")
    model = get_model()
    df = pd.read_csv(HISTORY_DB, low_memory=False)
    
    old_ha = model.home_advantage
    new_ha = model.optimize_home_advantage(df, 2024)
    print(f"   主场优势: {old_ha} → {new_ha}")
    
    # 重新训练 (用最新的完整数据)
    count = model.train(df, seasons=[2021, 2022, 2023, 2024, 2025])
    print(f"   重新训练: {count} 队")
    
    return {"home_advantage": new_ha, "teams": count}


def generate_weekly_md(week_start: str, week_end: str, results: list, 
                        opt_result: dict) -> str:
    week_num = datetime.strptime(week_start, "%Y-%m-%d").strftime("%Y-W%W")
    
    total_matches = sum(r["total"] for r in results)
    avg_acc = sum(r["accuracy"] * r["total"] for r in results) / total_matches if total_matches else 0
    avg_brier = sum(r["brier"] * r["total"] for r in results) / total_matches if total_matches else 0
    
    lines = [
        f"# 📈 周度复盘报告 — {week_num}",
        f"",
        f"> {week_start} ~ {week_end} | {len(results)} 个比赛日",
        f"",
        "## 本周总览",
        f"",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 总场次 | {total_matches} |",
        f"| 周准确率 | {avg_acc:.1%} |",
        f"| 周 Brier | {avg_brier:.4f} |",
        f"| 分析天数 | {len(results)} |",
        f"",
        "## 每日趋势",
        f"",
        f"| 日期 | 场次 | 准确率 | Brier |",
        f"|------|------|--------|-------|",
    ]
    
    for r in results:
        trend = "📈" if r["accuracy"] > avg_acc else ("📉" if r["accuracy"] < avg_acc - 0.05 else "➡️")
        lines.append(f"| {r['date']} | {r['total']} | {trend} {r['accuracy']:.0%} | {r['brier']:.4f} |")
    
    lines.extend([
        f"",
        "## 模型优化",
        f"",
        f"| 项目 | 变更 |",
        f"|------|------|",
        f"| 主场优势系数 | {opt_result.get('home_advantage', '?')} |",
        f"| 训练球队数 | {opt_result.get('teams', '?')} |",
        f"",
        "## 改进建议",
        f"",
    ])
    
    # 自动分析改进方向
    if avg_acc < 0.50:
        lines.append("- ⚠️ 准确率低于50%, 建议增加训练数据或调整特征")
    if avg_brier > 0.22:
        lines.append("- ⚠️ Brier Score 偏高, 概率校准需要改进")
    if avg_acc >= 0.55:
        lines.append("- ✅ 模型表现稳定, 继续保持")
    
    lines.extend([
        f"",
        "---",
        f"> 🤖 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ])
    
    return "\n".join(lines)


def main():
    week_start, week_end = get_week_dates()
    week_num = datetime.strptime(week_start, "%Y-%m-%d").strftime("%Y-W%W")
    
    print("=" * 60)
    print(f"  📈 周度复盘 & 自优化 — {week_num}")
    print(f"  {week_start} ~ {week_end}")
    print("=" * 60)
    print()
    
    # 收集本周数据
    print("📊 收集本周复盘数据...")
    results = collect_week_results(week_start, week_end)
    print(f"   ✅ {len(results)} 天有数据")
    
    # 自优化
    opt_result = optimize_model()
    
    # 生成报告
    print("\n📝 生成周报...")
    md = generate_weekly_md(week_start, week_end, results, opt_result)
    
    report_path = f"{REPORTS_DIR}/weekly/{week_num}_review.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"   ✅ {report_path}")
    
    # 同时存 JSON 供其他系统调用
    summary = {
        "week": week_num,
        "start": week_start,
        "end": week_end,
        "total_matches": sum(r["total"] for r in results),
        "accuracy": sum(r["accuracy"] * r["total"] for r in results) / sum(r["total"] for r in results) if results else 0,
        "optimization": opt_result,
        "generated": datetime.now().isoformat(),
    }
    json_path = f"{REPORTS_DIR}/weekly/{week_num}_summary.json"
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"   ✅ {json_path}")
    
    print(f"\n{'='*60}")
    print(f"  ✅ 周报完成!")
    print(f"  总场次: {sum(r['total'] for r in results)}")
    print(f"  周准确率: {summary['accuracy']:.1%}")
    print(f"  📄 {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
