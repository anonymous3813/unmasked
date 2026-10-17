from pathlib import Path
import re
from trafilatura import fetch_url, extract


class ClaimDetectionService:
    def __init__(self):
        keywords_path = Path(__file__).parent.parent / "claim_words.md"
        self.keywords = self._load_keywords(keywords_path)

    @staticmethod
    def _load_keywords(path: Path) -> list[str]:
        keywords = []

        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            keywords.append(line)

        return keywords

    def find_matches(self, text: str) -> list[str]:
        if not self.keywords:
            return []

        pattern = re.compile(
            r"\b(?:" + "|".join(re.escape(term) for term in self.keywords) + r")\b",
            re.IGNORECASE,
        )

        return [match.group() for match in pattern.finditer(text)]

    def analyze_url(self, url: str) -> list[str]:
        downloaded = fetch_url(url)

        if downloaded is None:
            raise RuntimeError(f"Failed to fetch URL: {url}")

        text = extract(
            downloaded,
            output_format="markdown",
            with_metadata=True,
        )

        if not text:
            raise RuntimeError(f"Failed to extract text from URL: {url}")

        return self.find_matches(text)