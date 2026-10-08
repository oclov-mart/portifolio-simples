"""Carrega o config.yaml com tudo que é específico do seu ambiente de NOC."""

from dataclasses import dataclass
from pathlib import Path

import yaml

SEVERIDADES = ["info", "baixa", "media", "alta", "desastre"]


@dataclass
class Aba:
    nome: str
    url: str
    # Explica ao Claude o que é essa tela e o que conta como alerta.
    instrucoes: str = ""
    recarregar: bool = True


@dataclass
class Formulario:
    url: str
    # Campos do formulário e como preenchê-los a partir de um alerta.
    instrucoes: str = ""


@dataclass
class WhatsApp:
    contato: str
    url: str = "https://web.whatsapp.com"
    # Placeholders: {severidade} {host} {descricao} {aba} {chamado}
    modelo_mensagem: str = (
        "[NOC] {severidade}: {host} - {descricao} (painel: {aba}). Chamado: {chamado}"
    )


@dataclass
class Config:
    abas: list[Aba]
    formulario: Formulario | None = None
    whatsapp: WhatsApp | None = None
    modelo: str = "claude-opus-5-5"
    esforco_agente: str = "high"
    esforco_monitoramento: str = "low"
    severidade_minima: str = "alta"
    confirmar_acoes: bool = True
    max_passos: int = 40
    intervalo_ciclo_seg: int = 300
    perfil_dir: Path = Path(".perfil-navegador")
    pasta_prints: Path = Path("prints")
    largura: int = 1280
    altura: int = 800
    headless: bool = False


def carregar_config(caminho: str | Path) -> Config:
    dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}
    nav = dados.pop("navegador", {}) or {}
    form = dados.pop("formulario_chamado", None)
    zap = dados.pop("whatsapp", None)

    cfg = Config(
        abas=[Aba(**a) for a in dados.pop("abas", [])],
        formulario=Formulario(**form) if form else None,
        whatsapp=WhatsApp(**zap) if zap else None,
        perfil_dir=Path(nav.get("perfil_dir", ".perfil-navegador")),
        pasta_prints=Path(nav.get("pasta_prints", "prints")),
        largura=nav.get("largura", 1280),
        altura=nav.get("altura", 800),
        headless=nav.get("headless", False),
        **{k: v for k, v in dados.items() if k in Config.__dataclass_fields__},
    )
    if cfg.severidade_minima not in SEVERIDADES:
        raise ValueError(f"severidade_minima deve ser uma de {SEVERIDADES}")
    return cfg
