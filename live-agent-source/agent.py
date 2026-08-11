
"""
直播运营数据智能分析 Agent
工作流: Excel 输入 → analyzer 处理 → Prompt 渲染 → LLM 推理 → Markdown 报告输出
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# 项目根目录
ROOT = Path(__file__).parent

from analyzer import analyze, to_markdown_summary
from llm_client import LLMClient
from thresholds import evaluate_thresholds, load_threshold_config, to_markdown_summary as thresholds_to_markdown


# ===== Prompt 加载 =====

def load_prompt(name: str) -> tuple[str, str]:
    """从 prompts/ 目录加载 Prompt 模板，返回 (system_prompt, user_template)"""
    prompt_file = ROOT / "prompts" / f"{name}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt 文件不存在: {prompt_file}")

    content = prompt_file.read_text(encoding="utf-8")

    parts = content.split("## System Prompt")
    if len(parts) < 2:
        raise ValueError(f"Prompt 格式错误，缺少 '## System Prompt' 标记: {name}")

    after_system = parts[1]

    # 以 "## Few-shot" 为界分割：之前是 system prompt（角色+规则+格式），之后是 user template（示例+数据占位）
    few_shot_idx = after_system.find("\n## Few-shot")
    if few_shot_idx > 0:
        system_prompt = after_system[:few_shot_idx].strip()
        user_template = after_system[few_shot_idx:].strip()
    else:
        system_prompt = after_system.strip()
        user_template = ""

    system_prompt = system_prompt.rstrip("\n-")
    return system_prompt, user_template


# ===== 模式配置 =====

MODES = {
    "daily": {
        "name": "日常总结",
        "prompt_file": "daily_summary",
        "description": "生成结构化日报，适合每场直播后使用",
    },
    "anomaly": {
        "name": "异常预警",
        "prompt_file": "anomaly_alert",
        "description": "检测异常指标并输出预警报告和响应动作",
    },
    "optimization": {
        "name": "优化建议",
        "prompt_file": "optimization",
        "description": "多维度诊断 + 可落地的优先级建议",
    },
    "all": {
        "name": "全量分析",
        "prompt_file": None,  # 特殊处理：跑全部三种
        "description": "依次运行全部三种模式，输出完整分析包",
    },
}


# ===== 核心 Agent =====

class LiveStreamAgent:
    """直播数据分析 Agent"""

    def __init__(self, api_key: str = None, threshold_config: str = None):
        self.llm = LLMClient(api_key=api_key)
        self.threshold_config = load_threshold_config(threshold_config)

    def run(self, excel_path: str, mode: str = "daily", output_dir: str = None) -> dict:
        """
        主流程:
        1. 调用 analyzer 解析 Excel
        2. 加载对应 Prompt 模板
        3. 注入数据 → 调用 LLM
        4. 保存报告
        """
        print(f"\n{'='*60}")
        print(f"  Agent 启动 — 模式: {MODES[mode]['name']}")
        print(f"  数据文件: {excel_path}")
        print(f"{'='*60}\n")

        # Step 1: 数据分析
        print("[1/4] 解析数据...")
        analysis = analyze(excel_path)
        analysis["阈值判定"] = evaluate_thresholds(analysis, self.threshold_config)
        summary_text = to_markdown_summary(analysis)
        threshold_summary = thresholds_to_markdown(analysis["阈值判定"])
        analysis_json = json.dumps(analysis, ensure_ascii=False, indent=2)

        # Step 2: 确定要跑的模式列表
        modes_to_run = ["daily", "anomaly", "optimization"] if mode == "all" else [mode]

        results = {}
        for m in modes_to_run:
            print(f"\n[2/4] 加载 Prompt 模板: {MODES[m]['prompt_file']}")
            system_prompt, user_template = load_prompt(MODES[m]["prompt_file"])

            # 注入数据
            user_prompt = user_template.replace("{analysis_json}", analysis_json)

            # Step 3: LLM 推理
            print(f"[3/4] 调用 LLM ({self.llm.model})...")
            temperature = 0.1 if m == "anomaly" else 0.4
            report = self.llm.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=2500,
            )

            # Step 4: 保存
            print(f"[4/4] 保存报告...")
            output_path = self._save_report(
                m, report, summary_text, threshold_summary, analysis, output_dir
            )
            results[m] = {"report": report, "path": output_path}
            print(f"  → 已保存: {output_path}")

        print(f"\n{'='*60}")
        print(f"  Agent 运行完成")
        print(f"{'='*60}\n")
        return results

    def _save_report(self, mode: str, report: str, summary: str,
                     threshold_summary: str, analysis: dict,
                     output_dir: str = None) -> Path:
        """保存报告为 Markdown 文件"""
        output_dir = Path(output_dir) if output_dir else ROOT / "output"
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{mode}_{timestamp}.md"
        filepath = output_dir / filename

        # 组装完整报告：数据摘要 + LLM 分析
        full_report = f"""# {MODES[mode]['name']}报告

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 数据来源：{analysis.get('数据来源', 'N/A')}
> 分析模式：{MODES[mode]['name']}

---

## 数据摘要

{summary}

---

## 程序阈值判定

{threshold_summary}

---

## AI 分析

{report}
"""
        filepath.write_text(full_report, encoding="utf-8")
        return filepath


# ===== CLI 入口 =====

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="直播运营数据智能分析 Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python agent.py data.xlsx                        # 默认日常总结
  python agent.py data.xlsx --mode anomaly         # 异常预警
  python agent.py data.xlsx --mode optimization    # 优化建议
  python agent.py data.xlsx --mode all             # 全量分析
  python agent.py data.xlsx --api-key sk-xxx       # 指定 API Key
        """,
    )
    parser.add_argument("excel", help="邀课记录 Excel 文件路径")
    parser.add_argument("--mode", choices=list(MODES.keys()), default="daily",
                        help="分析模式 (默认: daily)")
    parser.add_argument("--api-key", default=None,
                        help="LLM API Key (也可设置环境变量 LLM_API_KEY)")
    parser.add_argument("--output", default=None,
                        help="报告输出目录 (默认: ./output)")
    parser.add_argument("--threshold-config", default=None,
                        help="阈值配置文件路径 (默认: ./config/thresholds.json)")

    args = parser.parse_args()

    agent = LiveStreamAgent(api_key=args.api_key, threshold_config=args.threshold_config)
    agent.run(
        excel_path=args.excel,
        mode=args.mode,
        output_dir=args.output,
    )
