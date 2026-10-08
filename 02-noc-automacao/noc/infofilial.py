"""Dados da loja no sistema interno (localhost:8080/infofilial/N), lidos pelo print.

Telefone lido errado = mensagem para a pessoa errada. Por isso a página é lida
duas vezes, de forma independente, e os dados só são aceitos se as duas
leituras baterem.
"""

import logging
import re
import time

from pydantic import BaseModel, Field

from .navegador import Navegador
from .visao import TarefaFalhou, Visao

log = logging.getLogger(__name__)

VALIDADE_CACHE_SEG = 6 * 3600


class Circuito(BaseModel):
    operadora: str = Field(description="Nome da operadora como aparece (Vivo, Claro, Hexato, FBR...).")
    identificador: str = Field(description="ID/designação do circuito, exatamente como aparece.")


class Filial(BaseModel):
    numero_loja_na_tela: str = Field(description="Número da loja/filial mostrado na página.")
    nome: str
    cidade: str
    endereco: str
    telefone_loja: str
    email_loja: str
    gl_nome: str
    gl_telefone: str
    gr_nome: str
    gr_telefone: str
    circuitos: list[Circuito]

    def circuito_da(self, operadora: str) -> str:
        return next((c.identificador for c in self.circuitos
                     if c.operadora.strip().lower() == operadora.lower()), "")

    def campos(self) -> dict:
        """Campos disponíveis nos modelos de mensagem ({nome_loja}, {gl_nome}...)."""
        dados = self.model_dump(exclude={"circuitos", "numero_loja_na_tela"})
        dados["nome_loja"] = dados.pop("nome")
        return dados


PROMPT = """Este é um print da página de informações de uma filial (loja).
{instrucoes}

Transcreva os dados da loja. Telefones: copie todos os dígitos exatamente como \
aparecem, com DDD. GL = gerente da loja; GR = gerente regional. Liste todos os \
circuitos/links de internet com a operadora e o identificador. Campo ausente ou \
ilegível: deixe vazio."""

CAMPOS_CONFERIDOS = ("numero_loja_na_tela", "telefone_loja", "gl_telefone", "gr_telefone", "email_loja")


def _digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


class InfoFilial:
    def __init__(self, visao: Visao, nav: Navegador, cfg: dict):
        self.visao = visao
        self.nav = nav
        self.cfg = cfg["infofilial"]
        self._cache: dict[int, tuple[float, Filial]] = {}

    def buscar(self, loja: int) -> Filial:
        guardado = self._cache.get(loja)
        if guardado and time.time() - guardado[0] < VALIDADE_CACHE_SEG:
            return guardado[1]

        pagina = self.nav.ir("infofilial", self.cfg["url"].format(loja=loja))
        prompt = PROMPT.format(instrucoes=self.cfg["instrucoes"])
        leituras = [self.visao.ler(pagina, f"infofilial-{loja}", prompt, Filial) for _ in range(2)]
        for filial in leituras:
            for campo in ("telefone_loja", "gl_telefone", "gr_telefone"):
                setattr(filial, campo, _digitos(getattr(filial, campo)))

        a, b = leituras
        divergentes = [c for c in CAMPOS_CONFERIDOS if getattr(a, c) != getattr(b, c)]
        if divergentes:
            raise TarefaFalhou(f"infofilial {loja}: leituras divergentes em {divergentes}")
        if _digitos(a.numero_loja_na_tela).lstrip("0") != str(loja):
            raise TarefaFalhou(f"infofilial {loja}: a página mostra a loja {a.numero_loja_na_tela!r}")
        for campo in ("telefone_loja", "gl_telefone", "gr_telefone"):
            if getattr(a, campo) and len(getattr(a, campo)) not in (10, 11, 12, 13):
                log.warning("infofilial %s: %s com tamanho estranho (%s); ignorado",
                            loja, campo, getattr(a, campo))
                setattr(a, campo, "")

        self._cache[loja] = (time.time(), a)
        return a
