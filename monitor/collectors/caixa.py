from __future__ import annotations

from playwright.sync_api import Error as PlaywrightError

from .base import SiteAdapter, SourceUnavailable


class CaixaAdapter(SiteAdapter):
    max_pages = 1

    def prepare(self, page) -> None:
        # CAIXA exposes a public state-by-state download wizard. Select SC through
        # the visible form, without calling undocumented endpoints.
        selects = page.locator("select")
        if selects.count():
            for index in range(selects.count()):
                try:
                    selects.nth(index).select_option(label="Santa Catarina", timeout=2500)
                    break
                except PlaywrightError:
                    continue
            next_button = page.get_by_role("button", name="Próximo")
            if next_button.count():
                next_button.first.click(timeout=3000)
                page.wait_for_timeout(700)

    def collect(self, page):
        items, summary = super().collect(page)
        if summary["status"] == "failed" and "formato dos resultados" in (summary["error"] or ""):
            summary["error"] = "O catálogo público da CAIXA usa um assistente de download; o passo seguinte ainda precisa ser integrado."
        return items, summary
