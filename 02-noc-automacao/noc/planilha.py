"""Planilha de desastres no SharePoint (Excel Online), preenchida por teclado."""

import logging

from pydantic import BaseModel

from .navegador import Navegador
from .visao import TarefaFalhou, Visao

log = logging.getLogger(__name__)


class UltimaLinha(BaseModel):
    valores: list[str]  # células da última linha preenchida, da coluna A em diante


class Planilha:
    def __init__(self, visao: Visao, nav: Navegador, cfg: dict):
        self.visao = visao
        self.nav = nav
        self.cfg = cfg["planilha"]

    def registrar(self, valores: list[str], conferir: str) -> None:
        """Adiciona uma linha com `valores` e confere que `conferir` (ex.: nº da loja) ficou nela."""
        if not self.cfg["url"]:
            log.warning("planilha.url não configurada; registro de desastre ignorado")
            return
        pagina = self.nav.ir("planilha", self.cfg["url"], espera_ms=10_000)
        lista = "\n".join(f"   {i}. {v}" for i, v in enumerate(valores, 1))
        self.visao.executar(pagina, "planilha", f"""Esta é a planilha de desastres no \
Excel Online (SharePoint). Adicione UMA linha nova logo abaixo da última linha preenchida.
{self.cfg["instrucoes"]}
1. Clique na célula da coluna A da primeira linha vazia abaixo dos dados.
2. Digite os valores abaixo, um por coluna, da esquerda para a direita, apertando Tab \
entre eles (valor vazio = só aperte Tab):
{lista}
3. Ao final, aperte Enter.
Não altere nenhuma outra célula. Conclua com sucesso quando conferir no print que a \
linha nova está correta. Se a planilha não abrir em modo de edição, conclua com sucesso=false.""")

        ultima = self.visao.ler(pagina, "planilha-conferencia", """Este é um print de uma \
planilha no Excel Online. Transcreva as células da ÚLTIMA linha preenchida da tabela, da \
coluna A em diante.""", UltimaLinha)
        if not any(conferir in v for v in ultima.valores):
            raise TarefaFalhou(f"Planilha: a última linha não contém {conferir!r}: {ultima.valores}")
        log.info("Planilha de desastres atualizada (%s)", conferir)
