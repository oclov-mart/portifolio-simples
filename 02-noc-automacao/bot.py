"""Bot de NOC: um comando, roda sozinho.

    python bot.py              # roda o fluxo em loop até você apertar Ctrl+C
    python bot.py --uma-vez    # roda um ciclo só (bom para acompanhar o log)
    python bot.py --preparar   # 1ª vez: abre todos os sistemas para você fazer login
"""

import argparse
import logging
import time
from logging.handlers import RotatingFileHandler

import anthropic

from noc.config import carregar_config
from noc.navegador import Navegador
from noc.orquestrador import BotNOC

log = logging.getLogger("bot")


def configurar_log(verboso: bool) -> None:
    formato = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formato)
    arquivo = RotatingFileHandler("bot.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    arquivo.setFormatter(formato)
    raiz = logging.getLogger()
    raiz.setLevel(logging.DEBUG if verboso else logging.INFO)
    raiz.addHandler(console)
    raiz.addHandler(arquivo)
    for ruidoso in ("httpx", "httpx2", "httpcore", "anthropic"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)


def preparar(cfg: dict, nav: Navegador) -> None:
    """Abre cada sistema numa aba para você fazer os logins uma única vez."""
    urls = {
        "zabbix": cfg["zabbix"]["url_problemas"],
        "whatsapp": cfg["whatsapp"]["url"],
        "gmail": cfg["gmail"]["url"],
        "sumovision": cfg["sumovision"]["url"],
        "planilha": cfg["planilha"]["url"],
    }
    for nome, url in urls.items():
        if url:
            nav.ir(nome, url, espera_ms=0)
    input("\nFaça login em todas as abas (e escaneie o QR do WhatsApp).\n"
          "Os logins ficam salvos no perfil do bot. Aperte Enter para fechar... ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bot de NOC (Playwright + visão do Claude)")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--uma-vez", action="store_true", help="roda um ciclo e sai")
    parser.add_argument("--preparar", action="store_true", help="abre os sistemas para login")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    configurar_log(args.verbose)
    cfg = carregar_config(args.config)

    with Navegador(cfg) as nav:
        if args.preparar:
            preparar(cfg, nav)
            return

        # Lê ANTHROPIC_API_KEY do ambiente (ou o perfil do `ant auth login`).
        bot = BotNOC(cfg, anthropic.Anthropic(), nav)
        bot.whatsapp.aguardar_login()
        log.info("Bot iniciado. Ctrl+C para parar.")

        while True:
            inicio = time.monotonic()
            try:
                bot.ciclo()
            except KeyboardInterrupt:
                raise
            except anthropic.APIError as erro:
                log.error("Erro na API do Claude: %s", erro)
            except Exception:
                log.exception("Erro no ciclo")
                nav.print_erro("ciclo")
            if args.uma_vez:
                break
            espera = max(0, cfg["intervalo_ciclo_seg"] - (time.monotonic() - inicio))
            log.info("Próximo ciclo em %d s", espera)
            time.sleep(espera)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Bot encerrado.")
