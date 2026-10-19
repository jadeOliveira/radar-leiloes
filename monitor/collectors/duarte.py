from .base import SiteAdapter


class DuarteAdapter(SiteAdapter):
    """Public offer pages published by Duarte Leilões Oficiais."""

    max_pages = 30

    def prepare(self, page) -> None:
        # Duarte renders its search results asynchronously after the shell loads.
        page.locator('a[href*="/oferta/"]').first.wait_for(state="visible", timeout=10000)
