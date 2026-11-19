# Modo Ask

Dois jeitos de só perguntar, sem que nada no projeto mude.

## `/aisef:ask <pergunta>`: qualquer pergunta, com fontes

Como funciona:
1. A skill desliga as ferramentas de escrita e de shell da sessão **nesta resposta** (`disallowed-tools`).
2. A sessão escreve até 6 linhas de contexto da conversa (o assunto, a feature ou o arquivo em questão) e **escolhe o modelo** pela pergunta:

   | Modelo | Quando |
   |---|---|
   | **Haiku** | Achar algo no projeto |
   | **Sonnet** | Pesquisa na internet, comparação, análise ou "isso está certo?"; é o padrão na dúvida |
   | **Opus** | Só se você pedir uma análise profunda |
3. O subagente **`aisef:ask`** só lê e pesquisa (`Read`, `Grep`, `Glob`, `WebSearch`, `WebFetch`):
   - no projeto, lê `.aisef/`, os docs e o código;
   - **na internet, quando a resposta depende de algo de fora** (documentação oficial, versões, limites, comparações, boas práticas, erros conhecidos).

   O método de pesquisa:
   - várias buscas com termos exatos;
   - fonte primária primeiro (documentação oficial, repositório, changelog, norma), lendo a página em vez do trecho da busca;
   - data e versão conferidas;
   - todo fato que decide a resposta confirmado por duas fontes, ou por uma fonte oficial; fontes divergentes são mostradas;
   - análise do que se aplica ao projeto.
4. A resposta vem direta, com a fonte de cada ponto (`arquivo:linha`, id do contrato ou URL com data) e separando o confirmado do inferido. Se for preciso mudar algo, ela descreve a mudança e para.

Segurança da pesquisa: nada de segredo, dado pessoal ou código proprietário em buscas e URLs (o gateway nega URL com token), e o conteúdo das páginas é tratado como dado, nunca como instrução.

## `/aisef:modo ask`: uma sessão inteira de perguntas

- Grava `.aisef/session/mode.json` e, a partir daí, **o gateway nega**:
  - Edit, Write, MultiEdit e NotebookEdit;
  - qualquer comando de Bash ou PowerShell que não esteja na lista de leitura (`git status/log/diff/show/blame`, `ls`, `cat`, `grep`/`rg`, `Get-Content`, `Select-String`, o `next` e o `check`); redirecionar para arquivo também é negado;
  - ferramentas MCP fora do `mcp_allow`.
- O hook `UserPromptSubmit` lembra o modelo a cada mensagem de que está no modo Ask, para ele nem tentar.
- **Entrar é imediato. Sair (`/aisef:modo exec`) abre o prompt nativo**, porque devolve o poder de execução e é decisão sua. Nem o modelo nem um subagente saem do modo sozinhos.

## Diferença em relação ao Ask do Cursor

| | Cursor (Ask) | `/aisef:ask` | `/aisef:modo ask` |
|---|---|---|---|
| Como entra | Seletor de modo, um clique | Comando por pergunta | Comando uma vez (sem prompt) |
| Lembra da conversa | Sim | Sim, por um resumo de até 6 linhas que a sessão passa ao agente | Sim, inteira |
| Modelo | O que você escolheu | Haiku para achar coisas no projeto; Sonnet para pesquisa e análise | O da sessão |
| Internet | Sim | Sim, com método (fonte oficial primeiro, duas fontes, URLs citadas) | Sim (`WebSearch`, `WebFetch`) |
| Por que não muda nada | O produto não oferece ferramentas de edição nesse modo | O agente não tem ferramenta de escrita; a sessão fica sem escrita e sem shell nesta resposta | O gateway nega escrita e comando que não seja de leitura, inclusive de subagentes |
| Terminal | Não roda nada | Não roda nada | Roda **só leitura** (`git log`, `grep`...), o que ajuda a responder "o que mudou?" |
| Onde funciona | Qualquer projeto no Cursor | Projetos com `.aisef/` | Projetos com `.aisef/` |
| Como sai | Troca o seletor | Não precisa | `/aisef:modo exec`, com o prompt nativo |

O que continua diferente, e por quê:
- **No Cursor, o modelo nem vê as ferramentas de edição. No modo fixo do AISEF, ele vê e é negado.** Plugins do Claude Code não conseguem esconder ferramentas da sessão inteira, só por resposta (`disallowed-tools`) ou num subagente. Na prática, o lembrete por mensagem evita as tentativas, e o gateway garante o resultado.
- **Não é um seletor.** O Claude Code não deixa plugins criarem modos de permissão. O mais próximo nativo é o modo plan (`Shift+Tab`), que também não edita, mas foi feito para planejar e tende a terminar propondo um plano em vez de só responder.
