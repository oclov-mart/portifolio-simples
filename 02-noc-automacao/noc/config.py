"""Leitura do config.yaml.

Tudo que depende do seu ambiente (URLs, textos das mensagens, e-mails das
operadoras, colunas da planilha) fica no YAML. Os valores abaixo são os padrões
usados quando uma chave não aparece no arquivo.
"""

import copy
import re
from pathlib import Path

import yaml

PADROES = {
    "modelo": "claude-opus-5-5",
    "esforco_acao": "medium",     # cliques e preenchimentos
    "esforco_leitura": "low",     # leitura de telas
    "max_passos": 30,             # limite de rodadas por tarefa de interface
    "intervalo_ciclo_seg": 120,
    "leituras_confirmacao": 2,    # ciclos seguidos vendo o alarme antes de agir
    "ciclos_para_normalizar": 3,  # ciclos seguidos sem o alarme para dá-lo por resolvido
    "arquivo_estado": "estado.json",
    "navegador": {
        "perfil_dir": ".perfil-bot",
        "pasta_prints": "prints",
        "guardar_prints": False,  # True salva todo print enviado ao Claude
        "headless": False,
        "canal": None,            # None = Chromium do Playwright
        "executavel": None,
        "largura": 1280,
        "altura": 800,
    },
    "zabbix": {
        "url_problemas": "https://zabbix.pmenos.com.br/zabbix.php?action=problem.view",
        "instrucoes": "",
        "padrao_loja": r"(?i)\bEMP[\s_-]*0*(\d{1,5})",
        "padrao_icmp": r"(?i)icmp",
        "padrao_link": r"(?i)(link|interface|wan|circuito)",
        "minutos_link": 10,
        "minutos_sem_resposta": 30,
        "max_telas": 5,
        "mensagens": {},
    },
    "infofilial": {"url": "http://localhost:8080/infofilial/{loja}", "instrucoes": ""},
    "whatsapp": {
        "url": "https://web.whatsapp.com",
        "ddi": "55",
        "grupo_energia": "",
        "seletor_rascunho": "footer [contenteditable='true']",
        "seletor_titulo_conversa": "#main header",
        "mensagens": {},
    },
    "gmail": {"url": "https://mail.google.com/mail/u/0/", "cc_noc": [], "dias_busca_protocolo": 3,
              "extrafarma_a_partir_de": 7000,
              "email_loja_por_bandeira": {"pague_menos": "emp{loja}@pmenos.com.br",
                                          "extrafarma": "ef{loja}@pmenos.com.br"}},
    "sumovision": {
        "url": "https://sumovision.fbrlabs.com.br/",
        "instrucoes": "",
        "padrao_protocolo": r"FBR-PGM-\d+",
    },
    "planilha": {"url": "", "instrucoes": "", "colunas": []},
    "operadoras": {},
}

# Mensagens de WhatsApp precisam citar a loja: é o que a trava confere.
MENSAGENS_WHATSAPP = ["icmp_loja", "icmp_gestor", "link_loja", "link_gestor", "energia_grupo"]
MENSAGENS_ZABBIX = ["contato_icmp", "contato_link", "sem_resposta", "energia",
                    "email_enviado", "chamado_aberto"]


def _mesclar(base: dict, extra: dict) -> dict:
    for chave, valor in (extra or {}).items():
        if isinstance(valor, dict) and isinstance(base.get(chave), dict):
            _mesclar(base[chave], valor)
        else:
            base[chave] = valor
    return base


def validar(cfg: dict) -> None:
    """Falha logo na partida se faltar algo que faria o bot errar no meio do caminho."""
    erros = []
    for chave in MENSAGENS_WHATSAPP:
        texto = cfg["whatsapp"]["mensagens"].get(chave)
        if not texto:
            erros.append(f"whatsapp.mensagens.{chave} não definido")
        elif "{loja}" not in texto:
            erros.append(f"whatsapp.mensagens.{chave} precisa conter {{loja}} (trava de segurança)")
    for nome, op in cfg["operadoras"].items():
        if "PREENCHER" in str(op):
            erros.append(f"operadoras.{nome} ainda tem campos 'PREENCHER'")
        if op.get("canal") not in ("email", "sumovision"):
            erros.append(f"operadoras.{nome}.canal deve ser 'email' ou 'sumovision'")
        if op.get("canal") == "email":
            for campo in ("para", "assunto", "corpo", "padrao_protocolo"):
                if not op.get(campo):
                    erros.append(f"operadoras.{nome}.{campo} não definido")
            if op.get("padrao_protocolo"):
                re.compile(op["padrao_protocolo"])
    for chave in MENSAGENS_ZABBIX:
        if not cfg["zabbix"]["mensagens"].get(chave):
            erros.append(f"zabbix.mensagens.{chave} não definido")
    if not cfg["whatsapp"]["grupo_energia"]:
        erros.append("whatsapp.grupo_energia não definido")
    if erros:
        raise ValueError("Configuração inválida:\n- " + "\n- ".join(erros))


def carregar_config(caminho: str | Path) -> dict:
    dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}
    cfg = _mesclar(copy.deepcopy(PADROES), dados)
    validar(cfg)
    return cfg


class _Dados(dict):
    def __missing__(self, chave):
        return ""


def formatar(modelo: str, dados: dict) -> str:
    """Preenche {campos} do modelo; campo sem valor vira texto vazio."""
    return modelo.format_map(_Dados(dados)).strip()
