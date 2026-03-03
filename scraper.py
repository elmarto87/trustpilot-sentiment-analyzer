import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup


class TrustpilotScraper:
    """Scrapes reviews from a Trustpilot company page."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    def __init__(self, delay: float = 1.5):
        # Polite delay between requests to avoid rate limiting
        self.delay = delay

    def _get(self, url: str) -> BeautifulSoup:
        response = requests.get(url, headers=self.HEADERS, timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser")

    def _get_company_name(self, soup: BeautifulSoup) -> str:
        # Try multiple selectors — Trustpilot updates class names regularly
        candidates = [
            soup.find("span", class_=lambda c: c and "title_displayName" in c),
            soup.find("span", class_=lambda c: c and "displayName" in c),
            soup.find("h1"),
        ]
        for el in candidates:
            if el and el.get_text(strip=True):
                return el.get_text(strip=True)
        return "Company"

    def _get_page_count(self, soup: BeautifulSoup) -> int:
        nav = soup.find("nav", class_=lambda c: c and "pagination" in c)
        if not nav:
            return 1
        page_numbers = []
        for a in nav.find_all("a", href=True):
            match = re.search(r"page=(\d+)", a["href"])
            if match:
                page_numbers.append(int(match.group(1)))
        return max(page_numbers) if page_numbers else 1

    def _extract_reviews(self, soup: BeautifulSoup) -> list:
        reviews = []

        cards = soup.find_all("article", attrs={"data-service-review-card-paper": True})

        for card in cards:
            try:
                # Reviewer name — find all CDS_Typography_appearance-default spans,
                # skip the initials avatar (≤3 chars), take the first real name
                name_spans = card.find_all(
                    "span", class_=lambda c: c and "appearance-default" in c
                )
                reviewer = "Anonymous"
                for span in name_spans:
                    text = span.get_text(strip=True)
                    if len(text) > 3:
                        reviewer = text
                        break

                # Star rating from image alt text (e.g. "Rated 4 out of 5 stars")
                rating = None
                img = card.find("img", alt=lambda a: a and "Rated" in a)
                if img:
                    match = re.search(r"Rated (\d)", img["alt"])
                    if match:
                        rating = int(match.group(1))

                # Review body — Trustpilot removed separate titles; body is the full text
                body_el = card.find("p", attrs={"data-relevant-review-text-typography": True})
                if not body_el:
                    body_el = card.find("p", class_=lambda c: c and "body-l" in c)
                body = re.sub(r"\.{3}See more$", "", body_el.get_text(strip=True)).strip() if body_el else ""

                # Company response
                response_el = card.find("p", class_=lambda c: c and "message" in c)
                company_response = response_el.get_text(strip=True) if response_el else ""

                date_el = card.find("time")
                date = date_el.get("datetime", "") if date_el else ""

                if body:
                    reviews.append({
                        "reviewer": reviewer,
                        "rating": rating,
                        "review": body,
                        "company_response": company_response,
                        "date": date,
                    })
            except Exception:
                continue

        return reviews

    def scrape(self, url: str, max_pages: int = None) -> pd.DataFrame:
        """
        Scrape all reviews from a Trustpilot URL.

        Args:
            url: Trustpilot review page URL
                 e.g. https://www.trustpilot.com/review/example.com
                 Filter by star rating: append ?stars=1 for 1-star reviews only
            max_pages: Cap the number of pages scraped. None = scrape all.

        Returns:
            DataFrame with columns: reviewer, title, rating, review,
                                    company_response, date, company
        """
        print(f"Fetching: {url}")
        soup = self._get(url)
        company = self._get_company_name(soup)
        total_pages = self._get_page_count(soup)

        if max_pages:
            total_pages = min(total_pages, max_pages)

        print(f"Company : {company}")
        print(f"Pages   : {total_pages}")

        all_reviews = self._extract_reviews(soup)

        for page in range(2, total_pages + 1):
            time.sleep(self.delay)
            sep = "&" if "?" in url else "?"
            page_url = f"{url}{sep}page={page}"
            try:
                page_soup = self._get(page_url)
                page_reviews = self._extract_reviews(page_soup)
                all_reviews.extend(page_reviews)
                print(f"  Page {page}/{total_pages} — {len(page_reviews)} reviews")
            except Exception as e:
                print(f"  Page {page} failed: {e}")
                continue

        df = pd.DataFrame(all_reviews)
        df["company"] = company
        print(f"\nTotal reviews scraped: {len(df)}")
        return df
