"""Sumo Vision (FBR): abertura de chamado e captura do protocolo FBR-PGM-XXXX."""

import logging
import re

from pydantic import BaseModel

from .navegador import Navegador
from .visao import TarefaFalhou, Visao

log = logging.getLogger(__name__)


class ListaChamados(BaseModel):
    protocolos: list[str]  # de cima para baixo, como aparecem na lista


PROMPT_LISTA = """Este é um print da lista de chamados do Sumo Vision. Transcreva, de \
cima para baixo, os números de protocolo visíveis (formato FBR-PGM-XXXX), exatamente \
como aparecem."""


class SumoVision:
    def __init__(self, visao: Visao, nav: Navegador, cfg: dict):
        self.visao = visao
        self.nav = nav
        self.cfg = cfg["sumovision"]

    def _protocolos(self, pagina) -> list[str]:
        padrao = re.compile(self.cfg["padrao_protocolo"])
        lidos = self.visao.ler(pagina, "sumovision-lista", PROMPT_LISTA, ListaChamados).protocolos
        return [p.strip() for p in lidos if padrao.fullmatch(p.strip())]

    def abrir_chamado(self, titulo: str, circuito: str, descricao: str) -> str:
        pagina = self.nav.ir("sumovision", self.cfg["url"], espera_ms=3000)
        antes = set(self._protocolos(pagina))

        resultado = self.visao.executar(pagina, "sumovision-chamado", f"""No Sumo Vision:
1. Clique em "Abrir chamado".
2. Preencha os campos com exatamente estes valores:
   - Título: {titulo}
   - ID do circuito FBR: {circuito}
   - Descrição: {descricao}
3. Salve/envie o chamado.
{self.cfg["instrucoes"]}
Conclua com sucesso quando o novo chamado aparecer no topo da lista, com dado = o \
protocolo FBR-PGM dele. Se faltar algum campo ou aparecer erro, conclua com sucesso=false.""")

        # Confere com uma leitura independente: o protocolo tem que ser novo na lista.
        pagina.reload(wait_until="domcontentloaded")
        pagina.wait_for_timeout(3000)
        novos = [p for p in self._protocolos(pagina) if p not in antes]
        if novos:
            return novos[0]
        if resultado.dado.strip() and resultado.dado.strip() not in antes \
                and re.fullmatch(self.cfg["padrao_protocolo"], resultado.dado.strip()):
            return resultado.dado.strip()
        raise TarefaFalhou("Sumo Vision: chamado enviado, mas o protocolo novo não foi encontrado na lista")
