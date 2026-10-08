"""Gmail: envio dos chamados às operadoras e busca do protocolo na resposta.

O e-mail é aberto já preenchido pela URL de composição do Gmail (navegação
normal); o Claude confere os campos no print e clica em Enviar.
"""

import logging
import re
from urllib.parse import quote, urlencode

from .navegador import Navegador
from .visao import Visao

log = logging.getLogger(__name__)


class Gmail:
    def __init__(self, visao: Visao, nav: Navegador, cfg: dict):
        self.visao = visao
        self.nav = nav
        self.cfg = cfg["gmail"]

    def enviar(self, para: list[str], cc: list[str], assunto: str, corpo: str) -> None:
        url = self.cfg["url"] + "?" + urlencode({
            "view": "cm", "fs": "1", "tf": "1",
            "to": ",".join(para), "cc": ",".join(cc), "su": assunto, "body": corpo,
        }, quote_via=quote)
        pagina = self.nav.ir("gmail", url, espera_ms=5000)
        self.visao.executar(pagina, "gmail-envio", f"""A janela de novo e-mail do Gmail já \
está aberta e preenchida. Confira no print:
- "Para" contém: {", ".join(para)}
- Assunto: {assunto}
- O corpo do e-mail está preenchido.
Se estiver tudo certo, clique no botão "Enviar". Conclua com sucesso quando aparecer \
a confirmação "Mensagem enviada". Se algum campo estiver errado ou vazio, NÃO envie \
e conclua com sucesso=false explicando o que está errado.""")
        log.info("E-mail enviado: %s", assunto)

    def buscar_protocolo(self, assunto: str, padrao: str, operadora: str) -> str | None:
        """Procura a resposta da operadora pelo assunto e devolve o protocolo, se já houver."""
        busca = f'subject:"{assunto}" -from:me newer_than:{self.cfg["dias_busca_protocolo"]}d'
        pagina = self.nav.ir("gmail", self.cfg["url"] + "#search/" + quote(busca), espera_ms=5000)
        resultado = self.visao.executar(pagina, "gmail-protocolo", f"""Esta é uma busca no \
Gmail por respostas da operadora {operadora} ao e-mail "{assunto}".
- Se a lista de resultados estiver vazia, conclua com sucesso=true e dado vazio.
- Se houver resultado, abra a conversa mais recente e procure o número de \
protocolo/chamado informado pela operadora na resposta dela (não no nosso e-mail).
Conclua com sucesso=true e dado = o protocolo exatamente como escrito, ou dado vazio \
se a resposta ainda não trouxer protocolo.""")
        if not resultado.dado:
            return None
        achado = re.search(padrao, resultado.dado)
        if not achado:
            log.warning("Protocolo lido (%r) não bate com o padrão de %s; ignorado",
                        resultado.dado, operadora)
            return None
        return achado.group(1) if achado.groups() else achado.group(0)
