# 2. Automação de NOC (Python + Playwright + Claude)

Automatiza o fluxo de plantão de um NOC: **monitorar os painéis → abrir chamado → avisar o plantão no WhatsApp**.
O Playwright controla o navegador e tira prints, e a API do Claude lê os prints e decide os próximos cliques.

## Como o fluxo foi dividido

| Etapa | Função (`noc/fluxos.py`) | Como funciona |
|---|---|---|
| 1. Monitorar abas | `monitorar_abas()` | Recarrega cada painel, tira um print e o Claude devolve os alertas em JSON validado (`Alerta`: severidade, host, descrição). |
| 2. Filtrar | `filtrar_graves()` | Mantém só o que atinge a `severidade_minima` e descarta o que já foi tratado. |
| 3. Abrir chamado | `abrir_chamado()` | O agente preenche o formulário clicando e digitando com base nos prints, pede sua confirmação e devolve o número do chamado. |
| 4. Avisar no WhatsApp | `enviar_whatsapp()` | O agente abre a conversa do plantão e digita a mensagem montada pelo código (o texto não é inventado pelo modelo), mas só envia depois da sua confirmação. |
| Tudo junto | `executar_ciclo()` | Etapas 1 → 4 para cada alerta novo. |

### Módulos

- `noc/navegador.py`: abre o Chromium com **perfil persistente** (o login do WhatsApp e dos painéis fica salvo), gerencia as abas e salva os prints em `prints/`.
- `noc/agente.py`: loop **print → Claude decide → Playwright executa**, usando o *computer use toolset* da API. As ações do Claude (`left_click`, `type`, `key`, `scroll`…) viram `page.mouse` / `page.keyboard`.
- `noc/fluxos.py`: as etapas do NOC listadas acima.
- `noc/config.py`: lê o `config.yaml` (URLs, instruções de cada tela, contato do WhatsApp).

## Segurança

- **Confirmação humana:** antes de enviar um formulário ou uma mensagem, o agente chama `solicitar_confirmacao` e o terminal pede `s/N`. Para desligar, use `confirmar_acoes: false`, mas só depois de validar bem o fluxo.
- **Prompt injection:** o texto que aparece na tela (alertas, mensagens recebidas) é tratado como dado, não como instrução.
- **WhatsApp:** automatizar o WhatsApp Web pode violar os termos de uso e levar ao bloqueio do número. Prefira usar um número dedicado ao NOC ou, se possível, a API oficial do WhatsApp Business.
- `config.yaml`, `.perfil-navegador/` (cookies) e `prints/` ficam fora do git.

## Como usar

```bash
cd 02-noc-automacao
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp config.example.yaml config.yaml   # edite URLs, instruções e contato
export ANTHROPIC_API_KEY=sk-ant-...

python main.py abrir        # 1ª vez: faça login nos painéis e escaneie o QR do WhatsApp
python main.py monitorar    # só lista os alertas (não clica em nada)
python main.py ciclo        # monitorar -> chamado -> WhatsApp, uma vez
python main.py loop         # repete a cada intervalo_ciclo_seg
python main.py tarefa formulario "Abra um chamado de teste com prioridade baixa"
```

Use `-v` para ver cada ação executada no log.

## Ajustando para o seu NOC

O que mais influencia o resultado são os campos `instrucoes` no `config.yaml`. Neles você explica, como explicaria a um colega novo:
- em cada aba, o que conta como alerta e como ler a severidade;
- no formulário, o que vai em cada campo e qual é o botão final.

## Próximos passos

- Guardar os alertas já tratados em arquivo/SQLite (hoje ficam só na memória do `loop`).
- Registrar quando um alerta é resolvido e avisar a normalização no WhatsApp.
- Testar `esforco_agente: medium` para reduzir custo, caso a precisão continue boa.
