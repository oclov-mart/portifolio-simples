"""Zabbix operado só por tela: leitura dos alarmes por print, ack/unack por cliques."""

import logging

from pydantic import BaseModel

from .navegador import Navegador
from .regras import Alarme
from .visao import TarefaFalhou, Visao

log = logging.getLogger(__name__)


class TelaProblemas(BaseModel):
    tela_ok: bool  # False se pediu login, deu erro ou não é a tela de problemas
    observacao: str
    alarmes: list[Alarme]
    fim_da_lista: bool  # True se a última linha da tabela está visível no print


class EntradaHistorico(BaseModel):
    hora: str
    usuario: str
    mensagem: str
    acoes: str


class Historico(BaseModel):
    entradas: list[EntradaHistorico]


PROMPT_PROBLEMAS = """Este é um print da tela de problemas (Problems) do Zabbix.
{instrucoes}

Transcreva TODAS as linhas da tabela de problemas visíveis no print, de cima para \
baixo, com os textos exatamente como aparecem. Severidade pela cor/rótulo: Disaster = \
desastre, High = alta, Average = media, Warning = baixa, Information = info. \
Ignore linhas cortadas pela borda da tela. Se a tela não for a de problemas (login, \
erro, carregando), marque tela_ok=false e explique na observação."""


def descrever(alarme: Alarme) -> str:
    return (f'host "{alarme.host}", problema "{alarme.problema}", '
            f'início "{alarme.hora_inicio}"')


class Zabbix:
    def __init__(self, visao: Visao, nav: Navegador, cfg: dict):
        self.visao = visao
        self.nav = nav
        self.cfg = cfg["zabbix"]

    def _abrir(self):
        return self.nav.ir("zabbix", self.cfg["url_problemas"], espera_ms=3000)

    def ler_alarmes(self) -> list[Alarme]:
        """Lê a tabela de problemas, rolando a página se ela não couber em uma tela."""
        pagina = self._abrir()
        vistos: dict[str, Alarme] = {}
        for tela in range(1, self.cfg["max_telas"] + 1):
            leitura = self.visao.ler(pagina, "zabbix", PROMPT_PROBLEMAS.format(
                instrucoes=self.cfg["instrucoes"]), TelaProblemas)
            if not leitura.tela_ok:
                raise TarefaFalhou(f"Zabbix indisponível: {leitura.observacao}. Se for login, "
                                   "entre na janela do bot (a sessão fica salva).")
            for alarme in leitura.alarmes:
                vistos.setdefault(alarme.chave, alarme)
            if leitura.fim_da_lista:
                break
            pagina.mouse.move(640, 400)
            pagina.mouse.wheel(0, int(self.nav.cfg["altura"] * 0.7))
            pagina.wait_for_timeout(800)
        log.info("Zabbix: %d alarme(s) na tela", len(vistos))
        return list(vistos.values())

    def ler_historico(self, alarme: Alarme) -> Historico:
        """Abre o popup de atualização do alarme, lê o histórico e fecha sem alterar nada."""
        pagina = self._abrir()
        self.visao.executar(pagina, "zabbix-historico", f"""Na tabela de problemas do \
Zabbix, encontre a linha do alarme com {descrever(alarme)}. Clique no link da coluna \
Ack (ou "Update"/"Atualizar") dessa linha para abrir o popup de atualização do problema.
Não altere nada no popup. Conclua com sucesso quando o popup estiver aberto mostrando \
o histórico. Se não encontrar a linha, conclua com sucesso=false.""")
        historico = self.visao.ler(pagina, "zabbix-historico",
                                   "Transcreva a tabela de histórico (History) do popup aberto.", Historico)
        pagina.keyboard.press("Escape")
        return historico

    def atualizar(self, alarme: Alarme, mensagem: str, ack: bool | None) -> None:
        """Posta `mensagem` no alarme. ack=True reconhece, False remove o reconhecimento."""
        opcao = {
            True: 'marque a caixa "Acknowledge" (Reconhecer)',
            False: 'marque a caixa "Unacknowledge" (Remover reconhecimento)',
            None: "não altere as caixas de reconhecimento",
        }[ack]
        pagina = self._abrir()
        self.visao.executar(pagina, "zabbix-update", f"""Na tabela de problemas do Zabbix, \
encontre a linha do alarme com {descrever(alarme)}. Clique no link da coluna Ack \
(ou "Update"/"Atualizar") dessa linha para abrir o popup de atualização.
No popup:
1. Clique no campo "Message" (Mensagem) e digite exatamente o texto entre as linhas:
---
{mensagem}
---
2. {opcao}.
3. Clique no botão "Update" (Atualizar) do popup.
Conclua com sucesso quando o popup fechar sem mensagem de erro. Se não encontrar a \
linha ou aparecer erro, conclua com sucesso=false.""")
        log.info("Zabbix atualizado (ack=%s): %s", ack, alarme.host)
