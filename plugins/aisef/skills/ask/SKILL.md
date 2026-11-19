---
name: ask
description: 'Modo pergunta do AISEF: responde uma duvida sobre o projeto sem editar nem executar nada, com o subagente aisef:ask (Haiku, so leitura) e um resumo da conversa para ele saber do que se fala. Use quando o usuario digitar /aisef:ask ou fizer uma pergunta pedindo para nao mudar nada.'
argument-hint: "<sua pergunta>"
disallowed-tools: Edit, Write, MultiEdit, NotebookEdit, Bash, PowerShell
---

# aisef:ask

Pergunta do usuario: **$ARGUMENTS**

Voce nao responde lendo o projeto voce mesmo e nao muda nada: nesta resposta as ferramentas de escrita e de shell estao desligadas. Faca assim:

1. **Monte o contexto em ate 6 linhas**, so com o que ja esta nesta conversa: o assunto em discussao, a feature/fatia/arquivo citados e decisoes ja tomadas que importam para a pergunta. Sem segredos.
2. **Delegue** com UMA chamada da ferramenta Agent:
   - `subagent_type: "aisef:ask"` (Haiku, ferramentas so `Read`, `Grep`, `Glob`)
   - `description`: "Responder pergunta"
   - `prompt`: "Contexto da conversa:\n<as linhas do passo 1>\n\nPergunta: $ARGUMENTS"
   - em primeiro plano (sem `run_in_background`), porque o usuario espera a resposta.
3. **Repasse a resposta** do agente como ela veio, com as citacoes `arquivo:linha`/ids. Corte so repeticoes. Se ele disser que algo nao esta documentado, mantenha isso.
4. Se a resposta concluir que e preciso mudar algo, termine com uma linha: "Para fazer essa mudanca, e so pedir (ou `/aisef:modo exec`, se a sessao estiver no modo Ask)."
