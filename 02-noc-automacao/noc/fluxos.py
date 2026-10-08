"""As etapas do fluxo de NOC.

1. monitorar_abas   -> recarrega cada painel, tira print e o Claude extrai os alertas
2. abrir_chamado    -> o agente preenche o formulário de chamado para um alerta
3. enviar_whatsapp  -> o agente envia o aviso para o contato/grupo do plantão
4. executar_ciclo   -> junta tudo: alertas novos e graves viram chamado + aviso
"""

import base64
import logging
import re
from typing import Literal

import anthropic
from pydantic import BaseModel

from .agente import AgenteNavegador
from .config import SEVERIDADES, Config
from .navegador import Navegador

log = logging.getLogger(__name__)


class Alerta(BaseModel):
    severidade: Literal["info", "baixa", "media", "alta", "desastre"]
    host: str
    descricao: str
    desde: str | None = None  # horário/duração exibido no painel, se houver


class RelatorioAba(BaseModel):
    tela_ok: bool  # False se a tela não carregou, pediu login, deu erro etc.
    observacao: str
    alertas: list[Alerta]


class AlertaDetectado(Alerta):
    aba: str

    @property
    def chave(self) -> str:
        """Identifica o alerta para não abrir chamado duplicado."""
        return f"{self.aba}|{self.host}|{self.descricao}".lower()


PROMPT_MONITORAMENTO = """Este é um print da aba "{nome}" do NOC.
{instrucoes}

Liste os alertas/incidentes ativos visíveis na tela. Classifique a severidade \
como info, baixa, media, alta ou desastre, usando a cor/rótulo do próprio painel. \
Não invente alertas: se não houver nenhum, devolva a lista vazia. Se a tela não \
estiver utilizável (login, erro, carregando), marque tela_ok como false e explique."""


def monitorar_abas(cliente: anthropic.Anthropic, cfg: Config, nav: Navegador) -> list[AlertaDetectado]:
    """Etapa 1: varre as abas de monitoramento e devolve os alertas encontrados."""
    encontrados: list[AlertaDetectado] = []
    for aba in cfg.abas:
        pagina = nav.abrir_aba(aba.nome, aba.url)
        if aba.recarregar:
            # Painéis como Grafana/Zabbix nunca ficam "ociosos" na rede, então
            # espera o DOM e dá um tempo fixo para os gráficos renderizarem.
            pagina.reload(wait_until="domcontentloaded")
            pagina.wait_for_timeout(3000)
        png = nav.capturar_tela(pagina, f"monitor-{aba.nome}")

        resposta = cliente.messages.parse(
            model=cfg.modelo,
            max_tokens=16000,
            output_config={"effort": cfg.esforco_monitoramento},
            output_format=RelatorioAba,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/png",
                        "data": base64.b64encode(png).decode(),
                    }},
                    {"type": "text", "text": PROMPT_MONITORAMENTO.format(
                        nome=aba.nome, instrucoes=aba.instrucoes)},
                ],
            }],
        )
        if resposta.stop_reason == "refusal" or resposta.parsed_output is None:
            log.error("Não foi possível analisar a aba %s (stop_reason=%s)", aba.nome, resposta.stop_reason)
            continue

        relatorio = resposta.parsed_output
        if not relatorio.tela_ok:
            log.warning("Aba %s com problema: %s", aba.nome, relatorio.observacao)
        log.info("Aba %s: %d alerta(s)", aba.nome, len(relatorio.alertas))
        encontrados += [AlertaDetectado(aba=aba.nome, **a.model_dump()) for a in relatorio.alertas]
    return encontrados


def filtrar_graves(alertas: list[AlertaDetectado], severidade_minima: str) -> list[AlertaDetectado]:
    corte = SEVERIDADES.index(severidade_minima)
    return [a for a in alertas if SEVERIDADES.index(a.severidade) >= corte]


def abrir_chamado(agente: AgenteNavegador, cfg: Config, alerta: AlertaDetectado) -> str:
    """Etapa 2: preenche e envia o formulário de chamado. Devolve o número do chamado."""
    if not cfg.formulario:
        raise ValueError("Configure 'formulario_chamado' no config.yaml")
    agente.nav.abrir_aba("formulario", cfg.formulario.url).goto(cfg.formulario.url)
    tarefa = f"""Abra um chamado no formulário desta aba para o alerta abaixo.

Alerta:
- Painel: {alerta.aba}
- Severidade: {alerta.severidade}
- Host: {alerta.host}
- Descrição: {alerta.descricao}
- Desde: {alerta.desde or "não informado"}

Como preencher o formulário:
{cfg.formulario.instrucoes}

Antes de enviar, chame solicitar_confirmacao com todos os valores preenchidos. \
Termine a resposta com uma linha no formato "CHAMADO: <número ou protocolo exibido \
na tela>" (ou "CHAMADO: nenhum" se não foi aberto)."""
    resumo = agente.executar("formulario", tarefa)
    achado = re.search(r"CHAMADO:\s*(.+)", resumo)
    return achado.group(1).strip() if achado else resumo.strip()


def enviar_whatsapp(agente: AgenteNavegador, cfg: Config, mensagem: str) -> str:
    """Etapa 3: envia `mensagem` para o contato/grupo configurado no WhatsApp Web."""
    if not cfg.whatsapp:
        raise ValueError("Configure 'whatsapp' no config.yaml")
    agente.nav.abrir_aba("whatsapp", cfg.whatsapp.url)
    tarefa = f"""No WhatsApp Web desta aba, abra a conversa "{cfg.whatsapp.contato}" \
(use a busca de conversas) e envie exatamente o texto abaixo, sem alterar nada:

{mensagem}

Confira no print que a conversa aberta é "{cfg.whatsapp.contato}" e que o texto \
digitado está correto, chame solicitar_confirmacao e só então pressione Enter. \
Se o WhatsApp pedir para escanear o QR code, pare e avise."""
    return agente.executar("whatsapp", tarefa)


def montar_mensagem(cfg: Config, alerta: AlertaDetectado, chamado: str) -> str:
    return cfg.whatsapp.modelo_mensagem.format(
        severidade=alerta.severidade.upper(), host=alerta.host,
        descricao=alerta.descricao, aba=alerta.aba, chamado=chamado,
    )


def executar_ciclo(
    cliente: anthropic.Anthropic, cfg: Config, nav: Navegador,
    agente: AgenteNavegador, ja_tratados: set[str],
) -> None:
    """Etapa 4: um ciclo completo de monitoramento -> chamado -> aviso."""
    graves = filtrar_graves(monitorar_abas(cliente, cfg, nav), cfg.severidade_minima)
    novos = [a for a in graves if a.chave not in ja_tratados]
    log.info("%d alerta(s) grave(s), %d novo(s)", len(graves), len(novos))

    for alerta in novos:
        chamado = "não aberto"
        if cfg.formulario:
            chamado = abrir_chamado(agente, cfg, alerta)
            log.info("Chamado: %s", chamado)
        if cfg.whatsapp:
            log.info("WhatsApp: %s", enviar_whatsapp(agente, cfg, montar_mensagem(cfg, alerta, chamado)))
        ja_tratados.add(alerta.chave)
