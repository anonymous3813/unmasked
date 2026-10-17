
from pathlib import Path
import re
from trafilatura import fetch_url, extract

class ClaimDetectionService:
    def __init__(self, keywords_path: Path | None = None):
        if keywords_path is None:
            keywords_path = Path(__file__).parent.parent / "claim_words.txt"

        self.keywords = self._load_keywords(keywords_path)

    @staticmethod
    def _load_keywords(path: Path) -> dict[str, list[str]]:
        keywords: dict[str, list[str]] = {}
        category = None

        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("[") and line.endswith("]"):
                category = line[1:-1].lower()
                keywords[category] = []
            elif category is not None:
                keywords[category].append(line)

        return keywords

    def find_matches(self, text: str, category: str) -> list[str]:
        terms = self.keywords.get(category.lower(), [])

        if not terms:
            return []

        pattern = re.compile(
            r"\b(?:" + "|".join(re.escape(term) for term in terms) + r")\b",
            re.IGNORECASE,
        )

        return [match.group() for match in pattern.finditer(text)]

    def analyze_url(self, url: str, category: str) -> list[str]:
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

        return self.find_matches(text, category)

cds = ClaimDetectionService()
print(cds.keywords)
