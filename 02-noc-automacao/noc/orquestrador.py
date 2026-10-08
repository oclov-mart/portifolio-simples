"""Fluxo do NOC: Zabbix -> WhatsApp -> chamados (Gmail/Sumo Vision) -> energia/planilha.

Cada alarme vira uma ocorrência com uma fase, guardada no estado.json:

  ICMP (queda total):  observando -> novo -> aguardando_resposta -> energia ----------> concluido
                                                           \\-> chamados -> aguardando_protocolo -> concluido
  Link > N min:        observando -> novo -> aguardando_protocolo -> concluido

- "observando": só age depois de ver o mesmo alarme em N leituras seguidas, para
  não agir sobre um número de loja lido errado.
- Cada envio (WhatsApp, e-mail, chamado, update no Zabbix) é um "passo" que roda
  uma única vez, mesmo se o bot cair e voltar.
"""

import logging
import re
from datetime import datetime, timedelta

import anthropic

from .config import formatar
from .estado import Estado, agora, minutos_desde
from .gmail import Gmail
from .infofilial import Filial, InfoFilial
from .navegador import Navegador
from .planilha import Planilha
from .regras import Ocorrencia, bandeira_pelo_zabbix, classificar, resumir_energia
from .sumovision import SumoVision
from .visao import Visao
from .whatsapp import TravaSeguranca, WhatsApp
from .zabbix import Zabbix

log = logging.getLogger(__name__)

MAX_TENTATIVAS = 3


class PassoPendente(Exception):
    """Um passo falhou e será tentado de novo no próximo ciclo."""


class BotNOC:
    def __init__(self, cfg: dict, cliente: anthropic.Anthropic, nav: Navegador):
        self.cfg = cfg
        self.nav = nav
        visao = Visao(cliente, cfg, nav)
        self.zabbix = Zabbix(visao, nav, cfg)
        self.info = InfoFilial(visao, nav, cfg)
        self.whatsapp = WhatsApp(visao, nav, cfg)
        self.gmail = Gmail(visao, nav, cfg)
        self.sumo = SumoVision(visao, nav, cfg)
        self.planilha = Planilha(visao, nav, cfg)
        self.estado = Estado(cfg["arquivo_estado"])
        self._email_avisado: set[int] = set()

    # ---------- ciclo ----------

    def ciclo(self) -> None:
        ocorrencias = classificar(self.zabbix.ler_alarmes(), self.cfg)
        atuais = {o.chave: o for o in ocorrencias}
        log.info("%d ocorrência(s): %s", len(ocorrencias),
                 ", ".join(f"loja {o.loja} ({o.tipo})" for o in ocorrencias) or "nenhuma")

        for chave, reg in list(self.estado.ocorrencias.items()):
            if chave in atuais:
                reg["ausente"] = 0
            else:
                reg["ausente"] = reg.get("ausente", 0) + 1
                if reg["ausente"] >= self.cfg["ciclos_para_normalizar"]:
                    log.info("Loja %s (%s) normalizada", reg["loja"], reg["tipo"])
                    self.estado.encerrar(chave, "normalizado")
        self.estado.salvar()

        for o in ocorrencias:
            if self.estado.ja_encerrado(o.chave):
                continue
            reg = self.estado.ocorrencias.setdefault(o.chave, {
                "tipo": o.tipo, "loja": o.loja, "operadora": o.operadora,
                "fase": "observando", "vistos": 0, "criado_em": agora(),
                "passos": [], "iniciados": [], "tentativas": {}, "chamados": {},
            })
            reg["alarme"] = o.alarme.model_dump()
            try:
                self._tratar(o, reg)
            except PassoPendente as erro:
                log.warning("Loja %s: %s (nova tentativa no próximo ciclo)", o.loja, erro)
            except Exception:
                log.exception("Loja %s: erro ao tratar ocorrência %s", o.loja, o.tipo)
                self.nav.print_erro(f"loja{o.loja}")
            finally:
                self.estado.salvar()

    def _tratar(self, o: Ocorrencia, reg: dict) -> None:
        if reg["fase"] == "observando":
            reg["vistos"] += 1
            if reg["vistos"] < self.cfg["leituras_confirmacao"]:
                return
            if o.alarme.reconhecido:
                log.info("Loja %s: alarme já reconhecido por outra pessoa; o bot não vai tratar", o.loja)
                self.estado.encerrar(o.chave, "já reconhecido")
                return
            reg["fase"] = "novo"
        if reg["fase"] == "concluido":
            return

        filial = self.info.buscar(o.loja)
        dados = self._dados(o, filial, reg)
        if o.tipo == "icmp":
            self._fluxo_icmp(o, reg, filial, dados)
        else:
            self._fluxo_link(o, reg, filial, dados)

    # ---------- fluxos ----------

    def _fluxo_icmp(self, o: Ocorrencia, reg: dict, filial: Filial, dados: dict) -> None:
        msgs = self.cfg["zabbix"]["mensagens"]
        if reg["fase"] == "novo":
            self._avisar(reg, filial, "icmp", dados)
            self._uma_vez(reg, "zbx_contato", lambda: self.zabbix.atualizar(
                o.alarme, formatar(msgs["contato_icmp"], dados), ack=True))
            reg["contato_em"] = agora()
            reg["fase"] = "aguardando_resposta"
            return  # dá tempo para responderem

        if reg["fase"] == "aguardando_resposta":
            respostas = []
            for telefone in self._contatos(filial):
                respostas += self.whatsapp.respostas_sobre_energia(telefone, o.loja)
            situacao = resumir_energia(respostas)
            if situacao == "sim":
                log.info("Loja %s: falta de energia confirmada", o.loja)
                reg["fase"] = "energia"
            elif situacao == "nao":
                log.info("Loja %s: energia normal; abrindo chamados dos links", o.loja)
                reg["fase"] = "chamados"
            elif minutos_desde(reg["contato_em"]) > self.cfg["zabbix"]["minutos_sem_resposta"]:
                # Sem retorno: tira o ack para o alarme voltar a chamar atenção da equipe.
                self._uma_vez(reg, "zbx_sem_resposta", lambda: self.zabbix.atualizar(
                    o.alarme, formatar(msgs["sem_resposta"], dados), ack=False))
                return
            else:
                return

        if reg["fase"] == "energia":
            self._registrar_energia(o, reg, filial, dados)
            reg["fase"] = "concluido"
            return

        if reg["fase"] == "chamados":
            for operadora in self._operadoras_da_filial(filial):
                self._abrir_chamado(o, reg, filial, operadora, dados)
            reg["fase"] = "aguardando_protocolo"

        if reg["fase"] == "aguardando_protocolo":
            self._coletar_protocolos(o, reg, dados)

    def _fluxo_link(self, o: Ocorrencia, reg: dict, filial: Filial, dados: dict) -> None:
        if reg["fase"] == "novo":
            if o.operadora:
                self._abrir_chamado(o, reg, filial, o.operadora, dados)
                dados = self._dados(o, filial, reg)  # agora com o protocolo, se já houver
            else:
                log.warning("Loja %s: operadora do link não identificada em %r",
                            o.loja, o.alarme.problema)
            self._avisar(reg, filial, "link", dados)
            if not reg["chamados"]:
                # Sem chamado aberto não há Padrão 1/2: registra o contato e dá ack.
                self._uma_vez(reg, "zbx_contato", lambda: self.zabbix.atualizar(
                    o.alarme, formatar(self.cfg["zabbix"]["mensagens"]["contato_link"], dados), ack=True))
            reg["fase"] = "aguardando_protocolo"

        if reg["fase"] == "aguardando_protocolo":
            self._coletar_protocolos(o, reg, dados)

    # ---------- passos ----------

    def _uma_vez(self, reg: dict, passo: str, acao) -> None:
        """Executa `acao` uma única vez por ocorrência, mesmo com o bot reiniciando.

        - Falhou com erro: tenta de novo no próximo ciclo (até MAX_TENTATIVAS).
        - Interrompido no meio (bot fechado/travou): NÃO repete, para não duplicar
          mensagem/e-mail/chamado. Fica registrado no log para conferência manual.
        """
        if self.estado.feito(reg, passo):
            return
        if passo in reg["iniciados"]:
            log.error("Loja %s: passo '%s' foi interrompido numa execução anterior e não "
                      "será repetido. Confira manualmente se foi concluído.", reg["loja"], passo)
            self.estado.marcar(reg, passo)
            return
        reg["iniciados"].append(passo)
        self.estado.salvar()
        try:
            acao()
        except TravaSeguranca as erro:
            reg["iniciados"].remove(passo)
            log.error("TRAVA DE SEGURANÇA: %s", erro)
            self._contar_falha(reg, passo, erro)
        except Exception as erro:
            reg["iniciados"].remove(passo)
            self._contar_falha(reg, passo, erro)
        else:
            reg["iniciados"].remove(passo)
            self.estado.marcar(reg, passo)

    def _contar_falha(self, reg: dict, passo: str, erro: Exception) -> None:
        tentativas = reg["tentativas"][passo] = reg["tentativas"].get(passo, 0) + 1
        self.nav.print_erro(f"loja{reg['loja']}-{passo}")
        if tentativas >= MAX_TENTATIVAS:
            log.error("Loja %s: passo '%s' falhou %d vezes; desistindo dele: %s",
                      reg["loja"], passo, tentativas, erro)
            self.estado.marcar(reg, passo)
            return
        raise PassoPendente(f"passo '{passo}' falhou ({tentativas}/{MAX_TENTATIVAS}): {erro}")

    def _avisar(self, reg: dict, filial: Filial, tipo: str, dados: dict) -> None:
        """Manda a mensagem do tipo de queda para loja, GL e GR (cada um uma vez)."""
        destinos = [("loja", filial.telefone_loja, filial.nome, f"{tipo}_loja"),
                    ("GL", filial.gl_telefone, filial.gl_nome, f"{tipo}_gestor"),
                    ("GR", filial.gr_telefone, filial.gr_nome, f"{tipo}_gestor")]
        pendente, ja_enviados = None, set()
        for rotulo, telefone, nome, modelo in destinos:
            if not telefone:
                log.warning("Loja %s: sem telefone de %s na infofilial", reg["loja"], rotulo)
                continue
            if telefone in ja_enviados:  # GL e GR com o mesmo número
                continue
            ja_enviados.add(telefone)
            texto = formatar(self.cfg["whatsapp"]["mensagens"][modelo], dados | {"nome": nome})
            try:
                self._uma_vez(reg, f"wa_{tipo}_{rotulo}", lambda t=telefone, x=texto, r=rotulo:
                              self.whatsapp.enviar_para_numero(t, x, reg["loja"], r))
            except PassoPendente as erro:
                pendente = pendente or erro  # tenta os outros destinatários antes de parar
        if pendente:
            raise pendente

    def _abrir_chamado(self, o: Ocorrencia, reg: dict, filial: Filial, operadora: str, dados: dict) -> None:
        op = self.cfg["operadoras"][operadora]
        dados = dados | {"operadora": op.get("nome", operadora),
                         "circuito": filial.circuito_da(op.get("nome_infofilial", operadora))}

        def abrir():
            if op["canal"] == "email":
                assunto = formatar(op["assunto"], dados)
                cc = list(self.cfg["gmail"]["cc_noc"]) + list(op.get("cc", []))
                if dados["email_loja"]:
                    cc.append(dados["email_loja"])
                self.gmail.enviar(op["para"], cc, assunto, formatar(op["corpo"], dados))
                reg["chamados"][operadora] = {"canal": "email", "assunto": assunto,
                                              "circuito": dados["circuito"], "protocolo": None}
            else:
                protocolo = self.sumo.abrir_chamado(formatar(op["titulo"], dados), dados["circuito"],
                                                    formatar(op["descricao"], dados))
                reg["chamados"][operadora] = {"canal": "sumovision", "circuito": dados["circuito"],
                                              "protocolo": protocolo, "capturado_em": agora()}
                log.info("Loja %s: chamado FBR %s", o.loja, protocolo)

        self._uma_vez(reg, f"chamado_{operadora}", abrir)

        # Padrão 1: assim que o e-mail sai, registra no Zabbix que aguarda o protocolo.
        if (reg["chamados"].get(operadora) or {}).get("canal") == "email":
            texto = formatar(self.cfg["zabbix"]["mensagens"]["email_enviado"], dados)
            self._uma_vez(reg, f"zbx_email_{operadora}",
                          lambda: self.zabbix.atualizar(o.alarme, texto, ack=True))

    def _coletar_protocolos(self, o: Ocorrencia, reg: dict, dados: dict) -> None:
        """Procura no Gmail os protocolos que ainda faltam e registra no Zabbix."""
        for operadora, chamado in reg["chamados"].items():
            if chamado["protocolo"] is None and chamado["canal"] == "email":
                op = self.cfg["operadoras"][operadora]
                protocolo = self.gmail.buscar_protocolo(chamado["assunto"], op["padrao_protocolo"], operadora)
                if not protocolo:
                    continue
                chamado["protocolo"] = protocolo
                chamado["capturado_em"] = agora()
                self.estado.salvar()
                log.info("Loja %s: protocolo %s = %s", o.loja, operadora, protocolo)
            if chamado["protocolo"]:
                # Padrão 2: chamado aberto, com data/hora em que o protocolo foi obtido.
                quando = datetime.fromisoformat(chamado.get("capturado_em") or agora())
                texto = formatar(self.cfg["zabbix"]["mensagens"]["chamado_aberto"], dados | {
                    "operadora": op_nome(self.cfg, operadora), "protocolo": chamado["protocolo"],
                    "circuito": chamado.get("circuito", ""),
                    "data": quando.strftime("%d/%m/%Y"), "hora": quando.strftime("%H:%M")})
                self._uma_vez(reg, f"zbx_chamado_{operadora}",
                              lambda t=texto: self.zabbix.atualizar(o.alarme, t, ack=True))
        if all(c["protocolo"] for c in reg["chamados"].values()):
            reg["fase"] = "concluido"

    def _registrar_energia(self, o: Ocorrencia, reg: dict, filial: Filial, dados: dict) -> None:
        texto_zbx = formatar(self.cfg["zabbix"]["mensagens"]["energia"], dados)
        for alarme in [o.alarme, *o.relacionados]:
            self._uma_vez(reg, f"zbx_energia|{alarme.chave}",
                          lambda a=alarme: self.zabbix.atualizar(a, texto_zbx, ack=True))
        grupo = self.cfg["whatsapp"]["grupo_energia"]
        texto_grupo = formatar(self.cfg["whatsapp"]["mensagens"]["energia_grupo"], dados)
        self._uma_vez(reg, "wa_grupo_energia",
                      lambda: self.whatsapp.enviar_para_grupo(grupo, texto_grupo, o.loja))
        valores = [formatar(c, dados) for c in self.cfg["planilha"]["colunas"]]
        self._uma_vez(reg, "planilha", lambda: self.planilha.registrar(valores, conferir=str(o.loja)))

    # ---------- auxiliares ----------

    def _contatos(self, filial: Filial) -> list[str]:
        return list(dict.fromkeys(t for t in (filial.telefone_loja, filial.gl_telefone,
                                              filial.gr_telefone) if t))

    def _email_loja(self, filial: Filial, o: Ocorrencia) -> str:
        """E-mail da unidade para a cópia dos chamados.

        1. O e-mail mostrado na infofilial, se for válido.
        2. Senão, montado pela bandeira: Pague Menos = emp<nº>, Extrafarma = ef<nº>.
           A bandeira vem da infofilial ou, se lá não estiver clara, do Zabbix.
        3. Bandeira desconhecida: vazio (sem cópia para a loja). Não chuta, porque
           emp123 e ef123 são lojas diferentes.
        """
        email = filial.email_loja.strip()
        if re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", email):
            return email
        bandeira = (filial.bandeira if filial.bandeira != "desconhecida"
                    else bandeira_pelo_zabbix(o.alarme, self.cfg["zabbix"]["padroes_bandeira"]))
        modelo = self.cfg["gmail"]["email_loja_por_bandeira"].get(bandeira or "")
        reserva = formatar(modelo, {"loja": o.loja}) if modelo else ""
        if o.loja not in self._email_avisado:
            self._email_avisado.add(o.loja)
            motivo = f"inválido ({email!r})" if email else "ausente"
            if reserva:
                log.warning("Loja %s: e-mail da unidade %s na infofilial; bandeira %s -> %s",
                            o.loja, motivo, bandeira, reserva)
            else:
                log.warning("Loja %s: e-mail da unidade %s e bandeira desconhecida; chamados "
                            "seguem SEM a loja em cópia", o.loja, motivo)
        return reserva

    def _operadoras_da_filial(self, filial: Filial) -> list[str]:
        nomes = {c.operadora.strip().lower() for c in filial.circuitos}
        return [k for k, op in self.cfg["operadoras"].items()
                if op.get("nome_infofilial", k).lower() in nomes]

    def _dados(self, o: Ocorrencia, filial: Filial, reg: dict) -> dict:
        """Campos disponíveis nos textos do config.yaml."""
        agora_ = datetime.now()
        chamados = "; ".join(f"{op_nome(self.cfg, op)}: {c['protocolo'] or 'aguardando protocolo'}"
                             for op, c in reg["chamados"].items())
        operadora = o.operadora or ""
        return filial.campos() | {
            "email_loja": self._email_loja(filial, o),
            "loja": o.loja, "host": o.alarme.host, "problema": o.alarme.problema,
            "inicio": o.alarme.hora_inicio, "duracao": o.alarme.duracao,
            # A coluna de horário do Zabbix pode trazer só a hora; a data vem da duração.
            "data_inicio": (agora_ - timedelta(minutes=o.alarme.minutos)).strftime("%d/%m/%Y %H:%M"),
            "data": agora_.strftime("%d/%m/%Y"), "hora": agora_.strftime("%H:%M"),
            "operadora": op_nome(self.cfg, operadora) if operadora else "",
            "circuito": filial.circuito_da(self.cfg["operadoras"].get(operadora, {})
                                           .get("nome_infofilial", operadora)) if operadora else "",
            "protocolo": (reg["chamados"].get(operadora) or {}).get("protocolo") or "",
            "chamados": chamados or "nenhum",
            "energia_local": ("Sim, a loja segue comunicando pelo outro link" if o.tipo == "link"
                              else "Sim, confirmado pela loja/gestores"),
        }


def op_nome(cfg: dict, operadora: str) -> str:
    return cfg["operadoras"].get(operadora, {}).get("nome", operadora)
