"""Summarize PoliMillionaire math experiment logs without publishing quiz text.

Usage:
    python scripts/summarize_math_results.py --logs-dir /path/to/logs/experiments-math
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from html import escape
from pathlib import Path
from statistics import mean, median


SELECTED_RUNS = {
    "qwen3.5-4b-base.json": "Qwen 3.5 4B · baseline",
    "qwen3.5_4b_pythoneval.json": "Qwen 3.5 4B · Python",
    "qwen3.5_4b_simplecalc.json": "Qwen 3.5 4B · calculator",
    "qwen3.5_4b_eager_categorization_calc.json": "Qwen 3.5 4B · routing + calculator",
    "qwen3.5-4b-answer-then-verify.json": "Qwen 3.5 4B · answer + verify",
    "nemtron3-4b-base.json": "Nemotron 3 Nano 4B · baseline",
    "nemotron-3-nano_4b_eager_categorization_calc.json":
        "Nemotron 3 Nano 4B · routing + calculator",
}


def summarize(logs_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    selected_sessions = []

    for path in sorted(logs_dir.glob("*.json")):
        try:
            experiment = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        sessions = experiment.get("sessions", [])
        if not isinstance(sessions, list) or not sessions:
            continue

        scores = []
        timeouts = 0
        for number, session in enumerate(sessions, start=1):
            questions = session.get("questions") or []
            correct = sum(question.get("correct") is True for question in questions)
            timed_out = sum(question.get("timed_out") is True for question in questions)
            scores.append(correct)
            timeouts += timed_out

            if path.name in SELECTED_RUNS:
                selected_sessions.append(
                    {
                        "run": path.stem,
                        "session": number,
                        "correct_answers": correct,
                        "timed_out_questions": timed_out,
                        "reward": session.get("reward", ""),
                    }
                )

        summaries.append(
            {
                "run": path.stem,
                "sessions": len(scores),
                "mean_correct": round(mean(scores), 3),
                "median_correct": median(scores),
                "hit_at_10_pct": round(100 * sum(score >= 10 for score in scores) / len(scores), 2),
                "hit_at_15_pct": round(100 * sum(score >= 15 for score in scores) / len(scores), 2),
                "timed_out_questions": timeouts,
            }
        )

    if not summaries:
        raise SystemExit(f"No experiment sessions found in {logs_dir}")

    summary_path = output_dir / "math_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    sessions_path = output_dir / "math_selected_sessions.csv"
    with sessions_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["run", "session", "correct_answers", "timed_out_questions", "reward"],
        )
        writer.writeheader()
        writer.writerows(selected_sessions)

    if selected_sessions:
        by_run = {row["run"]: row for row in summaries}
        selected = [
            (filename, label, by_run[Path(filename).stem])
            for filename, label in SELECTED_RUNS.items()
            if Path(filename).stem in by_run
        ]
        width, left, plot_width = 1140, 405, 555
        height = 165 + 51 * len(selected)
        scale_max = max(1, math.ceil(max(row["mean_correct"] for _, _, row in selected)))
        svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
            '<title id="title">Math agent architectures: mean correct answers per game</title>',
            '<desc id="desc">Seven selected runs comparing Qwen 3.5 4B and Nemotron 3 Nano 4B with different tools and routing strategies.</desc>',
            f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
            '<text x="30" y="43" font-family="Arial, sans-serif" font-size="25" font-weight="700" fill="#17243b">Math agent architectures</text>',
            '<text x="30" y="69" font-family="Arial, sans-serif" font-size="15" fill="#536176">Mean correct answers per game · selected experiment runs</text>',
        ]
        for tick in range(scale_max + 1):
            x = left + plot_width * tick / scale_max
            svg.append(f'<line x1="{x:.1f}" y1="103" x2="{x:.1f}" y2="{height-75}" stroke="#e3e8ee"/>')
            svg.append(f'<text x="{x:.1f}" y="{height-52}" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#64748b">{tick}</text>')
        for position, (_, label, row) in enumerate(selected):
            y = 113 + position * 51
            bar_width = plot_width * row["mean_correct"] / scale_max
            color = "#3567a6" if label.startswith("Qwen") else "#c46845"
            svg.append(f'<text x="30" y="{y+24}" font-family="Arial, sans-serif" font-size="14" fill="#26374d">{escape(label)}</text>')
            svg.append(f'<rect x="{left}" y="{y}" width="{bar_width:.1f}" height="33" rx="4" fill="{color}"/>')
            svg.append(f'<text x="{left+bar_width+10:.1f}" y="{y+23}" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#26374d">{row["mean_correct"]:.2f}  <tspan font-weight="400" fill="#64748b">(n={row["sessions"]})</tspan></text>')
        svg.append(f'<text x="30" y="{height-18}" font-family="Arial, sans-serif" font-size="12" fill="#64748b">Descriptive comparison; run conditions and sample sizes differ. Source: project experiment logs.</text>')
        svg.append("</svg>")
        asset_dir = output_dir.parent / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        (asset_dir / "math-architectures.svg").write_text("\n".join(svg) + "\n", encoding="utf-8")

    print(f"Wrote {summary_path} and {sessions_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-dir", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "results"
    )
    arguments = parser.parse_args()
    summarize(arguments.logs_dir, arguments.output_dir)
