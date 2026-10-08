"""Janela dedicada do Chromium com perfil próprio e persistente.

O perfil fica em `.perfil-bot/`, separado do seu Chrome do dia a dia. Os logins
(Zabbix, WhatsApp, Gmail, Sumo Vision, SharePoint) ficam salvos ali entre
execuções, e o bot não disputa a sessão com o seu navegador principal.
"""

import io
import logging
import math
from datetime import datetime
from pathlib import Path

from PIL import Image
from playwright.sync_api import BrowserContext, Page, sync_playwright

log = logging.getLogger(__name__)

# Limites de imagem da API para os modelos atuais (lado maior e tokens visuais).
LADO_MAXIMO = 2576
PIXELS_MAXIMOS = 4600 * 28 * 28  # um pouco abaixo do limite de 4784 tokens visuais


def caber_no_limite(png: bytes) -> bytes:
    """Reduz a imagem, se preciso, para caber no limite da API."""
    img = Image.open(io.BytesIO(png))
    w, h = img.size
    escala = min(1.0, LADO_MAXIMO / max(w, h), math.sqrt(PIXELS_MAXIMOS / (w * h)))
    if escala >= 1.0:
        return png
    img = img.resize((int(w * escala), int(h * escala)), Image.LANCZOS)
    saida = io.BytesIO()
    img.save(saida, format="PNG")
    return saida.getvalue()


class Navegador:
    def __init__(self, cfg: dict):
        self.cfg = cfg["navegador"]
        self._pw = None
        self.contexto: BrowserContext | None = None
        self._abas: dict[str, Page] = {}

    def __enter__(self) -> "Navegador":
        self._pw = sync_playwright().start()
        opcoes = dict(
            user_data_dir=str(Path(self.cfg["perfil_dir"]).resolve()),
            headless=self.cfg["headless"],
            viewport={"width": self.cfg["largura"], "height": self.cfg["altura"]},
            # Renderiza em 2x: os prints "nítidos" de leitura ficam mais legíveis,
            # enquanto os prints de ação continuam em 1x (coordenadas = pixels CSS).
            device_scale_factor=2,
            locale="pt-BR",
            timezone_id="America/Fortaleza",
        )
        if self.cfg.get("canal"):
            opcoes["channel"] = self.cfg["canal"]
        if self.cfg.get("executavel"):
            opcoes["executable_path"] = self.cfg["executavel"]
        self.contexto = self._pw.chromium.launch_persistent_context(**opcoes)
        self.contexto.set_default_timeout(30_000)
        return self

    def __exit__(self, *exc) -> None:
        if self.contexto:
            self.contexto.close()
        if self._pw:
            self._pw.stop()

    def aba(self, nome: str) -> Page:
        """Devolve a aba `nome` (uma por sistema), criando-a se ainda não existir."""
        pagina = self._abas.get(nome)
        if pagina is None or pagina.is_closed():
            livres = [p for p in self.contexto.pages
                      if p.url == "about:blank" and p not in self._abas.values()]
            pagina = livres[0] if livres else self.contexto.new_page()
            self._abas[nome] = pagina
        pagina.bring_to_front()
        return pagina

    def ir(self, nome: str, url: str, espera_ms: int = 2000) -> Page:
        """Navega a aba `nome` até `url`, como digitar o endereço na barra."""
        pagina = self.aba(nome)
        log.debug("[%s] abrindo %s", nome, url)
        pagina.goto(url, wait_until="domcontentloaded")
        pagina.wait_for_timeout(espera_ms)
        return pagina

    def print(self, pagina: Page, rotulo: str, nitido: bool = False) -> bytes:
        """Print do que está visível na aba.

        nitido=False: 1 pixel do print = 1 pixel CSS (usado para clicar).
        nitido=True: resolução 2x reduzida ao limite da API (usado só para ler).
        """
        png = pagina.screenshot(type="png", scale="device" if nitido else "css")
        if nitido:
            png = caber_no_limite(png)
        if self.cfg["guardar_prints"]:
            self._salvar(png, rotulo)
        return png

    def print_erro(self, rotulo: str) -> None:
        """Salva um print de cada aba aberta para investigar uma falha depois."""
        for nome, pagina in self._abas.items():
            if pagina.is_closed():
                continue
            try:
                self._salvar(pagina.screenshot(type="png"), f"ERRO-{rotulo}-{nome}")
            except Exception:  # o print é só um extra; não pode derrubar o bot
                pass

    def _salvar(self, png: bytes, rotulo: str) -> None:
        pasta = Path(self.cfg["pasta_prints"])
        pasta.mkdir(parents=True, exist_ok=True)
        nome = "".join(c if c.isalnum() or c in "-_" else "_" for c in rotulo)
        (pasta / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{nome}.png").write_bytes(png)
