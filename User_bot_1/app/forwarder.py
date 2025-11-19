"""Keyword matching and message forwarding logic."""
import logging
import re

logger = logging.getLogger(__name__)


class KeywordForwarder:
    """Handles keyword matching and message forwarding."""

    def __init__(
        self,
        keywords: list[str],
        case_sensitive: bool = False,
        forwarding_enabled: bool = True,
    ):
        """
        Initialize keyword forwarder.

        Args:
            keywords: List of keywords to match
            case_sensitive: Whether matching should be case-sensitive
            forwarding_enabled: Whether to actually forward messages
        """
        self.keywords = keywords
        self.case_sensitive = case_sensitive
        self.forwarding_enabled = forwarding_enabled

        # Compile regex patterns for each keyword
        self.patterns = []
        for keyword in keywords:
            # Escape special regex characters
            escaped = re.escape(keyword)
            # Create word boundary pattern
            pattern = rf"\b{escaped}\b"
            flags = 0 if case_sensitive else re.IGNORECASE
            self.patterns.append(re.compile(pattern, flags))

        logger.info(
            f"Initialized forwarder with {len(keywords)} keywords "
            f"(case_sensitive={case_sensitive}, forwarding_enabled={forwarding_enabled})"
        )

    def contains_keywords(self, text: str) -> bool:
        """
        Check if text contains any of the keywords.

        Args:
            text: Text to check

        Returns:
            True if any keyword is found, False otherwise
        """
        if not text:
            return False

        for pattern in self.patterns:
            if pattern.search(text):
                return True

        return False

    def get_matched_keywords(self, text: str) -> list[str]:
        """
        Get list of keywords that match the text.

        Args:
            text: Text to check

        Returns:
            List of matched keywords
        """
        if not text:
            return []

        matched = []
        for keyword, pattern in zip(self.keywords, self.patterns):
            if pattern.search(text):
                matched.append(keyword)

        return matched