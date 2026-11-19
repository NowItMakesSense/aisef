---
name: ask
description: 'Modo pergunta do AISEF: responde qualquer duvida sem editar nem executar nada, lendo o projeto e pesquisando na internet com fontes quando preciso, pelo subagente aisef:ask com um resumo da conversa. Use quando o usuario digitar /aisef:ask ou fizer uma pergunta pedindo para nao mudar nada.'
argument-hint: "<sua pergunta>"
disallowed-tools: Edit, Write, MultiEdit, NotebookEdit, Bash, PowerShell
---

# aisef:ask

Pergunta do usuario: **$ARGUMENTS**

Voce nao responde pesquisando voce mesmo e nao muda nada: nesta resposta as ferramentas de escrita e de shell estao desligadas. Faca assim:

1. **Monte o contexto em ate 6 linhas**, so com o que ja esta nesta conversa: o assunto em discussao, a feature/fatia/arquivo citados e decisoes ja tomadas que importam para a pergunta. Sem segredos.
2. **Escolha o modelo** pela natureza da pergunta:
   - **`haiku`**: achar algo no projeto (onde esta X, o que faz Y, qual o estado da feature Z).
   - **`sonnet`**: precisa da internet (documentacao, versoes, comparacao, boas praticas, erro conhecido), de analise (vale a pena, esta certo, qual o risco) ou junta projeto e mundo externo. Na duvida, `sonnet`: precisao vale mais que economia numa resposta errada.
   - **`opus`**: so se o usuario pedir uma analise profunda ou a decisao for de alto impacto.
3. **Delegue** com UMA chamada da ferramenta Agent:
   - `subagent_type: "aisef:ask"` (so le e pesquisa: `Read`, `Grep`, `Glob`, `WebSearch`, `WebFetch`)
   - `model`: o escolhido no passo 2
   - `description`: "Responder pergunta"
   - `prompt`: "Contexto da conversa:\n<as linhas do passo 1>\n\nPergunta: $ARGUMENTS\n\nPesquise na internet se a resposta depender de algo de fora do projeto; cite as fontes."
   - em primeiro plano (sem `run_in_background`), porque o usuario espera a resposta.
4. **Repasse a resposta** do agente como ela veio, com as citacoes `arquivo:linha`/ids. Corte so repeticoes. Se ele disser que algo nao esta documentado, mantenha isso.
5. Se a resposta concluir que e preciso mudar algo, termine com uma linha: "Para fazer essa mudanca, e so pedir (ou `/aisef:modo exec`, se a sessao estiver no modo Ask)."
