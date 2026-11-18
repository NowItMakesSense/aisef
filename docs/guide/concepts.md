# Conceitos

O AISEF é um plugin do Claude Code que transforma pedidos em linguagem natural em trabalho de engenharia **especificado, executado por agentes, validado por outro agente e aceito por você**, com uma política de permissões aplicada em cada chamada de ferramenta e um log que denuncia adulteração.

Filosofia: **autonomia na execução, rigor na validação, controle humano nas decisões importantes.**

## As três camadas

| Camada | O que faz | Onde fica |
|---|---|---|
| **Processo** | Discovery → Feature Contract → Engineering Blueprint → Task Contracts → execução → validação independente → aceite. Requisitos rastreados de ponta a ponta (RTM). | Skills `aisef*` e geradores `aisef_new.py` |
| **Aplicação técnica** | O Execution Gateway (hook `PreToolUse`) classifica cada chamada (Bash, PowerShell, Read, Edit, Write, Grep, Glob, WebFetch, MCP) e devolve `allow`, `ask` ou `deny` conforme a política. | `hooks/gateway.py` + `core/permission-policy.v0.1.json` |
| **Evidência** | Toda operação, e toda tentativa negada ou levada à aprovação, vai para um log encadeado por hash e assinado com Ed25519. O head e a chave privada ficam fora do repositório. | `.aisef/audit/` + `~/.aisef/` |

## Vocabulário

- **Feature Contract**: o que a feature precisa fazer. Requisitos versionados com origem (`user_stated`, `investigated` ou `decision`; nunca inventados), regras de negócio, escopo e RTM.
- **Engineering Blueprint**: como construir. Componentes, endpoints, telas, entidades, migrações com rollback, ameaças, DevOps e testes, cada elemento apontando para requisitos.
- **Task Contract**: uma unidade de trabalho com critérios de aceite objetivos, paths permitidos, dependências e limites de tentativa.
- **Agent Contract**: o **teto** de permissões de cada agente. Nunca concede nada; só restringe.
- **Execution Report**: o que o agente fez, em JSON validado mais um relatório legível, com evidência para cada critério atendido.
- **Approval Center**: os pedidos que só você decide (plano, escopo, operação, reforçada, Git, arquitetura, mudança de escopo, aceite). A decisão passa pelo prompt nativo de permissão, que o modelo não consegue responder.
- **Aprovação reforçada**: uso único, até 30 minutos, para a **operação exata** (o comando literal), com diff, impacto, rollback e justificativa.
- **Estado efetivo**: o estado da tarefa combina o contrato com o último evento do log. É o que o `next` e o `check` usam.

## O que o AISEF não é

- **Não é uma fronteira de segurança.** O gateway lê comandos por padrões e reduz o risco. Use junto o sandbox do Claude Code (`/sandbox`) e as regras nativas que o `aisef-init` instala.
- **Não funciona fora do Claude Code.** Em Codex, Cursor ou Gemini, o `AGENTS.md` é só orientação.
- **Não decide por você.** Aprovações, aceite e operações Git continuam sendo suas, inclusive no modo contínuo.

## Onde cada coisa fica

| Caminho | O que é | Versionar? |
|---|---|---|
| `.aisef/contracts/`, `blueprints/`, `reports/` | Contratos, desenho técnico, relatórios | Sim |
| `.aisef/approvals/`, `authorizations/` | Pedidos e decisões | Sim |
| `.aisef/audit/` | Log encadeado e assinado (segmentos antigos em `archive/`) | Sim |
| `.aisef/knowledge/` | Memória de projeto, com fonte | Sim |
| `.aisef/panel/` | Painel gerado | Não (no `.gitignore`) |
| `~/.aisef/keys/`, `heads/`, `anchors/` | Chave privada, head e âncoras | Nunca no repositório |
