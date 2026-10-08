"""WhatsApp Web: avisos para loja/GL/GR, grupo de energia e leitura de respostas.

TRAVA DE SEGURANÇA (obrigatória): antes de apertar Enter, o código lê o texto do
campo de mensagem ([contenteditable]) direto do elemento, sem depender de
leitura de imagem, e só envia se:
  1. o número da loja aparece explicitamente no rascunho;
  2. o rascunho é exatamente a mensagem esperada.
Se algo não bater, o rascunho é apagado e nada é enviado.
"""

import logging
import re
import unicodedata
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel
from playwright.sync_api import TimeoutError as PWTimeout

from .navegador import Navegador
from .visao import TarefaFalhou, Visao, digitar

log = logging.getLogger(__name__)


class TravaSeguranca(Exception):
    """O rascunho não passou na conferência; a mensagem NÃO foi enviada."""


class MensagemConversa(BaseModel):
    enviada_por_mim: bool  # balão à direita (verde)
    texto: str
    sobre_energia: Literal["confirma_falta", "nega_falta", "nada"]


class Conversa(BaseModel):
    mensagens: list[MensagemConversa]


PROMPT_CONVERSA = """Este é um print de uma conversa aberta no WhatsApp Web.
Transcreva as mensagens visíveis, da mais antiga (em cima) para a mais recente (embaixo). \
enviada_por_mim=true para os balões à direita (enviados por nós).
Para cada mensagem recebida, classifique sobre_energia:
- confirma_falta: a pessoa confirma que está sem energia/luz na loja;
- nega_falta: a pessoa diz que a energia está normal na loja;
- nada: qualquer outra coisa (inclusive dúvidas, "vou verificar", áudio, foto).
Mensagens enviadas por nós: sempre "nada"."""


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos e com espaços simples, para comparar textos."""
    texto = unicodedata.normalize("NFKD", (texto or "").replace(" ", " "))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().lower()


def contem_numero_loja(texto: str, loja: int) -> bool:
    """True se o número da loja aparece isolado (não como parte de outro número)."""
    return re.search(rf"(?<!\d)0*{loja}(?!\d)", texto or "") is not None


class WhatsApp:
    def __init__(self, visao: Visao, nav: Navegador, cfg: dict):
        self.visao = visao
        self.nav = nav
        self.cfg = cfg["whatsapp"]

    # ---------- utilidades ----------

    def _numero(self, telefone: str) -> str:
        numero = re.sub(r"\D", "", telefone)
        if len(numero) in (10, 11):  # DDD + número, sem DDI
            numero = self.cfg["ddi"] + numero
        return numero

    def _pagina(self):
        return self.nav.aba("whatsapp")

    def _rascunho(self):
        return self._pagina().locator(self.cfg["seletor_rascunho"]).last

    def _limpar_rascunho(self) -> None:
        try:
            self._rascunho().click()
            self._pagina().keyboard.press("Control+A")
            self._pagina().keyboard.press("Backspace")
        except Exception:
            pass

    def aguardar_login(self, timeout_seg: int = 300) -> None:
        """Na 1ª execução é preciso escanear o QR code na janela do bot."""
        pagina = self.nav.ir("whatsapp", self.cfg["url"])
        try:
            pagina.wait_for_selector("#side", timeout=20_000)
        except PWTimeout:
            log.warning("WhatsApp: escaneie o QR code na janela do bot (aguardando %d s)", timeout_seg)
            pagina.wait_for_selector("#side", timeout=timeout_seg * 1000)

    def _abrir_por_numero(self, telefone: str, texto: str = "") -> None:
        url = f"{self.cfg['url'].rstrip('/')}/send?phone={self._numero(telefone)}"
        if texto:
            url += f"&text={quote(texto)}"
        pagina = self.nav.ir("whatsapp", url, espera_ms=1000)
        try:
            self._rascunho().wait_for(state="visible", timeout=60_000)
        except PWTimeout:
            raise TarefaFalhou(f"WhatsApp: a conversa com {telefone} não abriu "
                               "(número inválido ou sem WhatsApp?)") from None
        pagina.wait_for_timeout(1500)  # deixa o histórico renderizar

    # ---------- trava de segurança + envio ----------

    def _conferir_e_enviar(self, loja: int, esperado: str, destino: str) -> None:
        pagina = self._pagina()
        rascunho = self._rascunho()
        for _ in range(20):  # o texto do link ?text= às vezes demora a aparecer
            if rascunho.inner_text().strip():
                break
            pagina.wait_for_timeout(250)
        texto = rascunho.inner_text()

        if not contem_numero_loja(texto, loja):
            self._limpar_rascunho()
            raise TravaSeguranca(f"[{destino}] número da loja {loja} não está no rascunho; "
                                 f"envio cancelado. Rascunho: {texto!r}")
        if normalizar(texto) != normalizar(esperado):
            self._limpar_rascunho()
            raise TravaSeguranca(f"[{destino}] rascunho diferente do esperado; envio cancelado. "
                                 f"Rascunho: {texto!r}")

        enviadas = pagina.locator("#main div.message-out")
        antes = enviadas.count()
        rascunho.click()
        pagina.keyboard.press("Control+End")
        pagina.keyboard.press("Enter")
        try:
            enviadas.nth(antes).wait_for(state="attached", timeout=15_000)
        except PWTimeout:
            raise TarefaFalhou(f"[{destino}] a mensagem não apareceu como enviada") from None
        log.info("WhatsApp enviado -> %s", destino)

    def enviar_para_numero(self, telefone: str, mensagem: str, loja: int, destino: str) -> None:
        """Abre a conversa pelo número com o texto já no rascunho, confere e envia."""
        self._abrir_por_numero(telefone, mensagem)
        self._conferir_e_enviar(loja, mensagem, f"{destino} ({telefone})")

    def enviar_para_grupo(self, grupo: str, mensagem: str, loja: int) -> None:
        """Abre o grupo pela busca, digita com Shift+Enter entre as linhas, confere e envia."""
        pagina = self.nav.ir("whatsapp", self.cfg["url"], espera_ms=3000)
        self.visao.executar(pagina, "whatsapp-grupo", f"""No WhatsApp Web, use a caixa \
de pesquisa de conversas (no topo da lista à esquerda) para encontrar o grupo \
"{grupo}" e clique nele para abrir a conversa. Não digite nada no campo de mensagem. \
Conclua com sucesso quando o cabeçalho da conversa aberta mostrar exatamente "{grupo}".""")

        titulo = pagina.locator(self.cfg["seletor_titulo_conversa"]).first.inner_text()
        if normalizar(grupo) not in normalizar(titulo):
            raise TravaSeguranca(f"Conversa aberta não é o grupo '{grupo}' (cabeçalho: {titulo!r})")

        self._limpar_rascunho()
        self._rascunho().click()
        digitar(pagina, mensagem)
        self._conferir_e_enviar(loja, mensagem, f"grupo {grupo}")

    # ---------- leitura de respostas ----------

    def respostas_sobre_energia(self, telefone: str, loja: int) -> list[str]:
        """Classificações das mensagens recebidas depois do nosso último aviso sobre a loja."""
        self._abrir_por_numero(telefone)
        conversa = self.visao.ler(self._pagina(), "whatsapp-respostas", PROMPT_CONVERSA, Conversa)
        ultimo_aviso = max((i for i, m in enumerate(conversa.mensagens)
                            if m.enviada_por_mim and contem_numero_loja(m.texto, loja)), default=None)
        if ultimo_aviso is None:
            return []
        return [m.sobre_energia for m in conversa.mensagens[ultimo_aviso + 1:] if not m.enviada_por_mim]
