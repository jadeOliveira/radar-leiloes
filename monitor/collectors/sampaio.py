from .base import SiteAdapter


class SampaioAdapter(SiteAdapter):
    """Public auction listings from Sampaio Leilões."""

    max_pages = 30
