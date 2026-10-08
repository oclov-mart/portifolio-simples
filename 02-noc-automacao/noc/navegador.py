"""Navegador Playwright: abre as abas do NOC e tira prints.

Usa um perfil persistente, então o login do WhatsApp Web (QR code) e dos
painéis fica salvo entre execuções.
"""

import logging
from datetime import datetime
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

from .config import Config

log = logging.getLogger(__name__)


class Navegador:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._pw = None
        self.contexto: BrowserContext | None = None
        self.abas: dict[str, Page] = {}

    def __enter__(self) -> "Navegador":
        self._pw = sync_playwright().start()
        self.contexto = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.cfg.perfil_dir),
            headless=self.cfg.headless,
            # O viewport define o tamanho dos prints e o espaço de coordenadas
            # dos cliques do Claude. 1280x800 cabe no limite de imagem da API.
            viewport={"width": self.cfg.largura, "height": self.cfg.altura},
        )
        self.cfg.pasta_prints.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, *exc) -> None:
        if self.contexto:
            self.contexto.close()
        if self._pw:
            self._pw.stop()

    def abrir_aba(self, nome: str, url: str) -> Page:
        """Abre (ou reaproveita) uma aba identificada por nome."""
        if nome in self.abas and not self.abas[nome].is_closed():
            return self.abas[nome]
        # O contexto persistente já nasce com uma aba vazia: reaproveita.
        livres = [p for p in self.contexto.pages if p.url == "about:blank" and p not in self.abas.values()]
        pagina = livres[0] if livres else self.contexto.new_page()
        log.info("Abrindo aba %s: %s", nome, url)
        pagina.goto(url, wait_until="domcontentloaded")
        self.abas[nome] = pagina
        return pagina

    def abrir_todas(self) -> None:
        """Abre as abas de monitoramento, o formulário e o WhatsApp."""
        for aba in self.cfg.abas:
            self.abrir_aba(aba.nome, aba.url)
        if self.cfg.formulario:
            self.abrir_aba("formulario", self.cfg.formulario.url)
        if self.cfg.whatsapp:
            self.abrir_aba("whatsapp", self.cfg.whatsapp.url)

    def aba(self, nome: str) -> Page:
        return self.abas[nome]

    def capturar_tela(self, pagina: Page, rotulo: str) -> bytes:
        """Tira um print do viewport, salva em disco e devolve os bytes PNG."""
        pagina.bring_to_front()
        png = pagina.screenshot(type="png")
        carimbo = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        arquivo = Path(self.cfg.pasta_prints) / f"{carimbo}-{rotulo}.png"
        arquivo.write_bytes(png)
        log.debug("Print salvo em %s", arquivo)
        return png
