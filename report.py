import os
from datetime import datetime
from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd

SENTIMENT_COLORS = {
    "positive": "#2ecc71",
    "neutral": "#95a5a6",
    "negative": "#e74c3c",
}


class ReportGenerator:
    """Generates charts and a markdown report from analyzed review data."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def sentiment_chart(self, df: pd.DataFrame, company: str) -> str:
        counts = df["sentiment"].value_counts().reindex(
            ["positive", "neutral", "negative"], fill_value=0
        )
        colors = [SENTIMENT_COLORS[s] for s in counts.index]

        fig, ax = plt.subplots(figsize=(7, 5))
        bars = ax.bar(counts.index, counts.values, color=colors, edgecolor="white", linewidth=1.5)
        ax.set_title(f"Sentiment Distribution — {company}", fontsize=13, pad=12)
        ax.set_ylabel("Number of Reviews")
        ax.set_xlabel("Sentiment")
        for bar, val in zip(bars, counts.values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.5,
                str(val),
                ha="center", va="bottom", fontsize=11,
            )
        plt.tight_layout()
        path = os.path.join(self.output_dir, "sentiment_distribution.png")
        plt.savefig(path, dpi=150)
        plt.close()
        return path

    def theme_chart(self, df: pd.DataFrame, company: str) -> str:
        topic_sentiment = (
            df.groupby(["topic", "sentiment"])
            .size()
            .unstack(fill_value=0)
            .reindex(columns=["positive", "neutral", "negative"], fill_value=0)
        )
        topic_sentiment["total"] = topic_sentiment.sum(axis=1)
        top = topic_sentiment.nlargest(10, "total").drop(columns="total")

        fig, ax = plt.subplots(figsize=(10, 6))
        bottom = pd.Series([0] * len(top), index=top.index)
        for sentiment, color in SENTIMENT_COLORS.items():
            if sentiment in top.columns:
                ax.barh(
                    top.index, top[sentiment], left=bottom,
                    color=color, label=sentiment.capitalize(),
                )
                bottom = bottom + top[sentiment]

        ax.set_title(f"Top Topics by Frequency — {company}", fontsize=13, pad=12)
        ax.set_xlabel("Number of Reviews")
        ax.legend(loc="lower right")
        plt.tight_layout()
        path = os.path.join(self.output_dir, "topic_breakdown.png")
        plt.savefig(path, dpi=150)
        plt.close()
        return path

    def rating_trend_chart(self, df: pd.DataFrame, company: str) -> Optional[str]:
        if "date" not in df.columns or df["date"].isna().all():
            return None

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date", "rating"])
        if df.empty:
            return None

        monthly = df.set_index("date")["rating"].resample("ME").mean()

        fig, ax = plt.subplots(figsize=(10, 4))
        monthly.plot(ax=ax, marker="o", color="#3498db", linewidth=2)
        ax.set_title(f"Average Rating Over Time — {company}", fontsize=13, pad=12)
        ax.set_ylabel("Average Star Rating")
        ax.set_ylim(1, 5)
        ax.axhline(3, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
        plt.tight_layout()
        path = os.path.join(self.output_dir, "rating_trend.png")
        plt.savefig(path, dpi=150)
        plt.close()
        return path

    def generate_report(self, df: pd.DataFrame, insights: dict) -> str:
        """
        Generate charts and a markdown report file.

        Returns:
            The markdown report as a string.
        """
        company = df["company"].iloc[0] if "company" in df.columns else "Company"
        total = len(df)
        sc = df["sentiment"].value_counts()
        avg_rating = df["rating"].dropna().mean()

        self.sentiment_chart(df, company)
        self.theme_chart(df, company)
        self.rating_trend_chart(df, company)

        lines = [
            f"# Trustpilot Sentiment Analysis — {company}",
            f"*Generated {datetime.now().strftime('%Y-%m-%d')} | {total} reviews analyzed*",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Total reviews | {total} |",
            f"| Average rating | {avg_rating:.1f} / 5 |",
            f"| Positive | {sc.get('positive', 0)} "
            f"({sc.get('positive', 0)/total*100:.0f}%) |",
            f"| Neutral | {sc.get('neutral', 0)} "
            f"({sc.get('neutral', 0)/total*100:.0f}%) |",
            f"| Negative | {sc.get('negative', 0)} "
            f"({sc.get('negative', 0)/total*100:.0f}%) |",
            "",
            "![Sentiment Distribution](sentiment_distribution.png)",
            "",
            "![Topic Breakdown](topic_breakdown.png)",
            "",
        ]

        if insights.get("top_themes"):
            lines += ["## Top Themes", ""]
            for t in insights["top_themes"]:
                lines.append(
                    f"**{t.get('theme', '')}** "
                    f"— {t.get('sentiment_skew', '')} skew"
                )
                lines.append(f"{t.get('summary', '')}")
                lines.append("")

        if insights.get("biggest_pain_points"):
            lines += ["## Biggest Pain Points", ""]
            for p in insights["biggest_pain_points"]:
                lines.append(f"- {p}")
            lines.append("")

        if insights.get("strongest_strengths"):
            lines += ["## Strongest Strengths", ""]
            for s in insights["strongest_strengths"]:
                lines.append(f"- {s}")
            lines.append("")

        if insights.get("pm_recommendations"):
            lines += ["## PM Recommendations", ""]
            for i, r in enumerate(insights["pm_recommendations"], 1):
                lines.append(f"**{i}.** {r}")
                lines.append("")

        report = "\n".join(lines)
        report_path = os.path.join(self.output_dir, "report.md")
        with open(report_path, "w") as f:
            f.write(report)

        print(f"\nReport  → {report_path}")
        print(f"Charts  → {self.output_dir}/")
        return report
