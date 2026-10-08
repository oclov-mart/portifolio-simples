# 2. Bot de NOC (Python + Playwright + visão do Claude)

Roda o fluxo de plantão do NOC com **um comando** (`python bot.py`), operando os sistemas
**só pela tela**: o Playwright tira um print, o Claude lê a imagem e devolve comandos de
mouse/teclado ("clique em x,y", "digite T"), e o Playwright os executa como um usuário real.
Nenhum script é injetado nos sistemas e nenhuma API interna é chamada.

## Fluxo

```
Zabbix (print) ──► regras.py ──┬─ ICMP caído (queda total da loja)
                               │    ├─ WhatsApp: pergunta de energia para loja, GL e GR + ack no Zabbix
                               │    ├─ resposta "sem energia" ──► ack ENERGIA no Zabbix, aviso no grupo
                               │    │                             de energia e linha na planilha
                               │    ├─ resposta "tem energia" ──► chamados de todos os links da loja
                               │    └─ 30 min sem resposta ─────► unack + mensagem no Zabbix
                               │
                               └─ Link específico caído há > 10 min
                                    ├─ chamado: e-mail (Vivo/Claro/Hexato) ou Sumo Vision (FBR)
                                    ├─ WhatsApp para loja, GL e GR + ack no Zabbix
                                    └─ protocolo da resposta no Gmail ──► registrado no Zabbix
```

## Como cada sistema é operado

| Sistema | Leitura (print → JSON) | Ação (mouse/teclado) |
|---|---|---|
| **Zabbix** | Tabela de problemas, rolando a página se precisar; histórico do popup | Abre o popup do alarme, digita a mensagem, marca Ack/Unack, clica em Update |
| **Infofilial** | Telefones, GL, GR e circuitos, **lidos duas vezes** e aceitos só se as leituras baterem | — |
| **WhatsApp** | Respostas recebidas, classificadas como confirma/nega falta de energia | Abre `web.whatsapp.com/send?phone=…&text=…`, confere e envia; no grupo, digita com Shift+Enter |
| **Gmail** | Protocolo na resposta da operadora | Abre a URL de composição preenchida, confere os campos e clica em Enviar |
| **Sumo Vision** | Protocolos `FBR-PGM-XXXX` no topo da lista (antes e depois) | Abrir chamado → título, ID do circuito, descrição → salvar |
| **Planilha (SharePoint)** | Última linha, para conferir | Preenche a linha nova com Tab entre as colunas |

## Proteções (o bot roda sem ninguém validando)

- **Trava do WhatsApp:** antes do Enter, o código lê o texto do campo `[contenteditable]` direto
  do elemento (sem depender da leitura da imagem) e só envia se **o número da loja aparece no
  rascunho** e o rascunho é **exatamente** a mensagem esperada. Se não bater, apaga o rascunho e
  não envia. No grupo de energia, confere também o nome da conversa aberta. A partida do bot
  falha se algum texto de WhatsApp do `config.yaml` não tiver `{loja}`.
- **Leitura confirmada:** o bot só age sobre um alarme visto em 2 leituras seguidas do Zabbix
  (`leituras_confirmacao`), para não agir sobre um número de loja lido errado.
- **Telefones conferidos:** a infofilial é lida duas vezes e precisa mostrar o número da loja pedida.
- **Sem duplicidade:** cada envio (mensagem, e-mail, chamado, update) é um passo registrado no
  `estado.json`. Se o bot cair e voltar, continua de onde parou sem repetir nada. Um passo
  interrompido no meio do envio **não é repetido** e fica no log para você conferir.
- **Falha não trava o resto:** um passo que falha é tentado de novo nos ciclos seguintes, até 3
  vezes, e os demais seguem normalmente. Erros salvam prints em `prints/` e vão para o `bot.log`.
- **Alarme já reconhecido por outra pessoa** não é tratado pelo bot.
- Textos que aparecem nas telas (e-mails, mensagens recebidas) são tratados como dados, nunca
  como instruções para o bot.

## Como usar

```bash
cd 02-noc-automacao
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp config.example.yaml config.yaml    # preencha e-mails das operadoras, textos, planilha...
export ANTHROPIC_API_KEY=sk-ant-...

python bot.py --preparar   # 1ª vez: abre os sistemas para você logar e escanear o QR do WhatsApp
python bot.py              # roda sozinho em loop (Ctrl+C para parar)
```

Outras opções: `--uma-vez` roda um ciclo só; `-v` mostra cada clique no log.

A janela do bot usa um **perfil próprio** (`.perfil-bot/`), separado do seu Chrome: os logins
ficam salvos ali e não interferem no seu navegador. Para usar o Chrome instalado (ainda com
perfil separado), descomente `canal: chrome` no config.

## Configuração

Tudo que é específico do seu ambiente está no `config.yaml`:

- **`zabbix.url_problemas`:** use um filtro salvo com só lojas, ICMP e links, **sem esconder os
  reconhecidos**, porque o bot precisa continuar vendo o alarme depois de dar ack.
- **`padrao_loja`, `padrao_icmp`, `padrao_link`:** como identificar loja, ICMP e link no host/alarme.
- **`whatsapp.mensagens`, `zabbix.mensagens`:** os textos. Todos os de WhatsApp precisam ter `{loja}`.
- **`operadoras`:** destinatários, assunto, corpo (com a assinatura obrigatória da Claro) e o
  padrão do protocolo na resposta de cada uma. Os e-mails estão como `PREENCHER`.
- **`planilha.colunas`:** o valor de cada coluna da planilha de desastres, na ordem.
- **`instrucoes`** (Zabbix, infofilial, Sumo Vision, planilha): dicas em texto livre sobre a
  tela, caso o bot erre algo específico do seu sistema.

Campos disponíveis nos textos: `{loja} {nome_loja} {cidade} {endereco} {telefone_loja}
{email_loja} {gl_nome} {gl_telefone} {gr_nome} {gr_telefone} {horario_funcionamento} {energia_local} {host} {problema} {inicio}
{duracao} {data_inicio} {data} {hora} {operadora} {circuito} {protocolo} {chamados} {nome}` (`{nome}` =
destinatário da mensagem).

## Estrutura

```
bot.py               comando único: janela dedicada, login do WhatsApp, loop
noc/visao.py         núcleo: ler() print→JSON e executar() print→clique/digitação→print
noc/regras.py        regras de negócio em Python puro (ICMP x link, energia)
noc/orquestrador.py  máquina de estados por alarme e passos sem duplicidade
noc/estado.py        estado.json (sobrevive a reinícios)
noc/zabbix.py · infofilial.py · whatsapp.py · gmail.py · sumovision.py · planilha.py
```

## Limitações conhecidas

- Operar por visão é mais lento que por código: cada passo é print + resposta da API. Um envio
  pelo Gmail ou um update no Zabbix leva de dezenas de segundos a cerca de um minuto.
- Cada ação gasta várias chamadas à API. As leituras usam esforço `low`; se a precisão estiver
  boa, dá para testar `esforco_acao: low` para baratear.
- A leitura de respostas no WhatsApp considera só as mensagens visíveis na conversa aberta.
- O bot foi testado com páginas que imitam os sistemas, não com o Zabbix, WhatsApp, Gmail,
  Sumo Vision e SharePoint reais. Acompanhe o `bot.log` nas primeiras execuções.
