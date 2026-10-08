"""Memória do bot em disco (estado.json).

Guarda, por alarme, em que fase está o tratamento e quais passos já foram
feitos. Se o bot cair no meio (rede, travamento), ao voltar ele continua de
onde parou sem repetir mensagem, e-mail ou chamado.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

DIAS_ARQUIVO = 2  # por quanto tempo lembrar de alarmes já encerrados


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def minutos_desde(iso: str) -> float:
    return (datetime.now() - datetime.fromisoformat(iso)).total_seconds() / 60


class Estado:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.dados = {"ocorrencias": {}, "arquivo": {}}
        if self.caminho.exists():
            self.dados = json.loads(self.caminho.read_text(encoding="utf-8"))
        self._limpar_arquivo()

    @property
    def ocorrencias(self) -> dict[str, dict]:
        return self.dados["ocorrencias"]

    def salvar(self) -> None:
        temporario = self.caminho.with_suffix(".tmp")
        temporario.write_text(json.dumps(self.dados, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporario, self.caminho)  # troca atômica: o arquivo nunca fica pela metade

    def ja_encerrado(self, chave: str) -> bool:
        return chave in self.dados["arquivo"]

    def encerrar(self, chave: str, motivo: str) -> None:
        registro = self.ocorrencias.pop(chave, None)
        self.dados["arquivo"][chave] = {"em": agora(), "motivo": motivo,
                                        "fase": registro and registro.get("fase")}
        self.salvar()

    def feito(self, registro: dict, passo: str) -> bool:
        return passo in registro.setdefault("passos", [])

    def marcar(self, registro: dict, passo: str) -> None:
        registro.setdefault("passos", []).append(passo)
        self.salvar()  # grava na hora: o passo não se repete mesmo se o bot cair em seguida

    def _limpar_arquivo(self) -> None:
        limite = datetime.now() - timedelta(days=DIAS_ARQUIVO)
        self.dados["arquivo"] = {k: v for k, v in self.dados["arquivo"].items()
                                 if datetime.fromisoformat(v["em"]) > limite}
