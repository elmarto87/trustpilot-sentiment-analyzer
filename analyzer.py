import json
import math
import os
from typing import Optional, Tuple

import pandas as pd
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()


class ReviewAnalyzer:
    """
    Analyzes Trustpilot reviews using Claude.

    Two-model strategy:
    - claude-haiku  → batch sentiment tagging (fast, cheap, high volume)
    - claude-sonnet → theme synthesis + PM recommendations (better reasoning)
    """

    BATCH_SIZE = 25

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        self.client = Anthropic(api_key=api_key)

    def _tag_batch(self, reviews: list) -> list:
        """Send a batch of reviews to Claude Haiku for sentiment + topic tagging."""
        numbered = "\n\n".join(
            f"[{i+1}] Rating: {r.get('rating', '?')}/5\n"
            f"Title: {r.get('title', '')}\n"
            f"Review: {r.get('review', '')}"
            for i, r in enumerate(reviews)
        )

        prompt = (
            f"Analyze these {len(reviews)} customer reviews. "
            f"Return a JSON array with exactly {len(reviews)} objects.\n\n"
            "Each object must have:\n"
            '- "index": review number (1-based)\n'
            '- "sentiment": one of "positive", "neutral", "negative"\n'
            '- "topic": 2-4 word label for the main subject '
            '(e.g. "pricing transparency", "delivery speed", "customer service")\n'
            '- "key_point": one sentence capturing the core praise or complaint\n\n'
            "Return ONLY a valid JSON array, no other text.\n\n"
            f"Reviews:\n{numbered}"
        )

        message = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            return json.loads(message.content[0].text)
        except json.JSONDecodeError:
            return [
                {"index": i + 1, "sentiment": "neutral", "topic": "unknown", "key_point": ""}
                for i in range(len(reviews))
            ]

    def tag_reviews(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add sentiment, topic, and key_point columns to the DataFrame."""
        records = df.to_dict("records")
        tags = []
        total_batches = math.ceil(len(records) / self.BATCH_SIZE)

        for i in range(total_batches):
            batch = records[i * self.BATCH_SIZE:(i + 1) * self.BATCH_SIZE]
            print(f"  Tagging batch {i+1}/{total_batches} ({len(batch)} reviews)...")
            tags.extend(self._tag_batch(batch))

        tags_sorted = sorted(tags, key=lambda x: x.get("index", 0))
        df = df.copy()
        df["sentiment"] = [t.get("sentiment", "neutral") for t in tags_sorted][:len(df)]
        df["topic"] = [t.get("topic", "unknown") for t in tags_sorted][:len(df)]
        df["key_point"] = [t.get("key_point", "") for t in tags_sorted][:len(df)]
        return df

    def extract_insights(self, df: pd.DataFrame) -> dict:
        """Use Claude Sonnet to synthesize themes and generate PM recommendations."""
        sentiment_counts = df["sentiment"].value_counts().to_dict()
        topic_counts = df["topic"].value_counts().head(20).to_dict()
        sample_negatives = (
            df[df["sentiment"] == "negative"]["key_point"]
            .dropna()
            .head(10)
            .tolist()
        )
        sample_positives = (
            df[df["sentiment"] == "positive"]["key_point"]
            .dropna()
            .head(10)
            .tolist()
        )

        prompt = (
            "You are a senior PM analyzing customer review data for a product team.\n\n"
            f"Total reviews: {len(df)}\n"
            f"Sentiment breakdown: {json.dumps(sentiment_counts)}\n"
            f"Top topics by frequency: {json.dumps(topic_counts, indent=2)}\n\n"
            "Sample negative key points:\n"
            + "\n".join(f"- {p}" for p in sample_negatives)
            + "\n\nSample positive key points:\n"
            + "\n".join(f"- {p}" for p in sample_positives)
            + "\n\nReturn a JSON object with:\n"
            '- "top_themes": list of 5 objects, each with "theme" (name), '
            '"sentiment_skew" (positive/negative/mixed), "summary" (1 sentence)\n'
            '- "biggest_pain_points": list of 3 strings\n'
            '- "strongest_strengths": list of 3 strings\n'
            '- "pm_recommendations": list of 3 actionable recommendations '
            "with rationale (each as a single string)\n\n"
            "Return ONLY valid JSON, no other text."
        )

        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            return json.loads(message.content[0].text)
        except json.JSONDecodeError:
            return {}

    def analyze(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
        """
        Full analysis pipeline.

        Returns:
            tagged_df: DataFrame with sentiment, topic, key_point columns added
            insights:  Dict with top_themes, pain_points, strengths, pm_recommendations
        """
        print("Step 1/2: Tagging individual reviews (Haiku)...")
        tagged_df = self.tag_reviews(df)
        print("Step 2/2: Synthesizing themes and PM insights (Sonnet)...")
        insights = self.extract_insights(tagged_df)
        return tagged_df, insights
