"""Automação do fluxo de NOC com Playwright + API do Claude.

Exemplos:
    python main.py abrir                 # abre todas as abas (faça login/QR code)
    python main.py monitorar             # um print de cada painel -> lista de alertas
    python main.py ciclo                 # monitorar -> chamado -> WhatsApp, uma vez
    python main.py loop                  # repete o ciclo a cada intervalo_ciclo_seg
    python main.py tarefa formulario "Abra um chamado de teste com severidade baixa"
"""

import argparse
import logging
import time

import anthropic

from noc.agente import AgenteNavegador
from noc.config import carregar_config
from noc.fluxos import executar_ciclo, monitorar_abas
from noc.navegador import Navegador


def main() -> None:
    parser = argparse.ArgumentParser(description="Automação de NOC com Claude")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("abrir", help="abre as abas e espera Enter (para fazer login)")
    sub.add_parser("monitorar", help="lista os alertas de todas as abas")
    sub.add_parser("ciclo", help="executa um ciclo completo")
    sub.add_parser("loop", help="executa ciclos continuamente")
    tarefa = sub.add_parser("tarefa", help="tarefa livre para o agente em uma aba")
    tarefa.add_argument("aba")
    tarefa.add_argument("texto")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # A biblioteca httpx é muito verbosa no nível DEBUG.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    cfg = carregar_config(args.config)
    # Lê ANTHROPIC_API_KEY do ambiente (ou o perfil do `ant auth login`).
    cliente = anthropic.Anthropic()

    with Navegador(cfg) as nav:
        nav.abrir_todas()
        agente = AgenteNavegador(cliente, cfg, nav)

        if args.comando == "abrir":
            input("Abas abertas. Faça os logins necessários e pressione Enter para sair...")
        elif args.comando == "monitorar":
            for alerta in monitorar_abas(cliente, cfg, nav):
                print(f"[{alerta.severidade.upper():8}] {alerta.aba}: {alerta.host} - {alerta.descricao}")
        elif args.comando == "ciclo":
            executar_ciclo(cliente, cfg, nav, agente, set())
        elif args.comando == "loop":
            ja_tratados: set[str] = set()
            while True:
                try:
                    executar_ciclo(cliente, cfg, nav, agente, ja_tratados)
                except anthropic.APIError as erro:
                    # Rede/limite de uso: registra e tenta de novo no próximo ciclo.
                    logging.error("Erro na API do Claude: %s", erro)
                time.sleep(cfg.intervalo_ciclo_seg)
        elif args.comando == "tarefa":
            print(agente.executar(args.aba, args.texto))


if __name__ == "__main__":
    main()
