"""Regras de negócio do NOC, em Python puro (sem navegador e sem IA).

O Claude só lê as telas; quem decide o que é queda total, o que é link e quem
deve ser avisado é este módulo, que é previsível e pode ser testado.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

MINUTOS_POR_UNIDADE = {"y": 525_600, "M": 43_200, "w": 10_080, "d": 1_440,
                       "h": 60, "m": 1, "s": 1 / 60}


class Alarme(BaseModel):
    """Uma linha da tela de problemas do Zabbix, como lida no print."""
    hora_inicio: str = Field(description="Coluna de horário do início do problema, exatamente como na tela.")
    host: str
    problema: str
    severidade: Literal["desastre", "alta", "media", "baixa", "info", "desconhecida"]
    duracao: str = Field(description="Coluna de duração, exatamente como na tela (ex.: '1h 5m 3s').")
    reconhecido: bool = Field(description="true se a coluna Ack/Reconhecido indica Sim/Yes.")

    @property
    def chave(self) -> str:
        """Identifica o alarme entre ciclos (o eventid não aparece na tela)."""
        return f"{self.host}|{self.problema}|{self.hora_inicio}".lower()

    @property
    def minutos(self) -> float:
        return duracao_em_minutos(self.duracao)


@dataclass
class Ocorrencia:
    """Um caso a tratar: queda total da loja (ICMP) ou link específico caído."""
    tipo: Literal["icmp", "link"]
    loja: int
    alarme: Alarme
    operadora: str | None = None
    relacionados: list[Alarme] = field(default_factory=list)

    @property
    def chave(self) -> str:
        return self.alarme.chave


def duracao_em_minutos(texto: str) -> float:
    """'1d 2h 3m' -> 1563. O Zabbix usa 'M' para meses e 'm' para minutos."""
    return sum(int(n) * MINUTOS_POR_UNIDADE[u]
               for n, u in re.findall(r"(\d+)\s*([yMwdhms])(?![a-zA-Z])", texto or ""))


def numero_loja(host: str, padrao: str) -> int | None:
    m = re.search(padrao, host or "")
    return int(m.group(1)) if m else None


def classificar(alarmes: list[Alarme], cfg: dict) -> list[Ocorrencia]:
    """Separa queda total (ICMP) de link específico caído há mais de N minutos.

    Se a loja está com ICMP caído, os alarmes de link dela entram como
    relacionados da ocorrência ICMP: provavelmente têm a mesma causa.
    """
    z = cfg["zabbix"]
    icmp, link = re.compile(z["padrao_icmp"]), re.compile(z["padrao_link"])
    operadoras = {nome: re.compile(op.get("padrao_zabbix") or re.escape(nome), re.I)
                  for nome, op in cfg["operadoras"].items()}

    por_loja: dict[int, list[Alarme]] = {}
    for a in alarmes:
        loja = numero_loja(a.host, z["padrao_loja"])
        if loja is not None:
            por_loja.setdefault(loja, []).append(a)

    ocorrencias = []
    for loja, lista in por_loja.items():
        quedas = [a for a in lista if icmp.search(a.problema)]
        links = [a for a in lista if link.search(a.problema) and not icmp.search(a.problema)]
        if quedas:
            principal = max(quedas, key=lambda a: a.minutos)  # o mais antigo
            ocorrencias.append(Ocorrencia("icmp", loja, principal, relacionados=links))
            continue
        for a in links:
            if a.minutos >= z["minutos_link"]:
                operadora = next((n for n, rx in operadoras.items() if rx.search(a.problema)), None)
                ocorrencias.append(Ocorrencia("link", loja, a, operadora=operadora))
    return ocorrencias


def resumir_energia(respostas: list[str]) -> Literal["sim", "nao"] | None:
    """Junta as classificações das respostas de loja/GL/GR.

    Basta uma confirmação de falta de energia para valer "sim"; "nao" só se
    alguém negou e ninguém confirmou.
    """
    if "confirma_falta" in respostas:
        return "sim"
    if "nega_falta" in respostas:
        return "nao"
    return None
