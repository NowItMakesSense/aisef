# Comandos

Todos ficam em `plugins/aisef/core/` (chamado `CORE` nas skills) e rodam com `python -I`. As skills chamam esses comandos por você. Esta página é para quem quer entender ou depurar.

## `aisef_project.py`: estado do projeto e log

| Comando | Para quê |
|---|---|
| `init --project . --project-id ID --name N --environment dev` | Cria `.aisef/`, o log e as chaves (a privada fica em `~/.aisef/`) |
| `append --type T --summary S [--actor ...] [--feature F] [--task T] [--corrects E-ID]` | Anexa um marco ao log. Recusa ator errado antes de gravar |
| `request --file rascunho.json` | Registra um pedido no Approval Center (valida, anexa `approval_requested`) |
| `decide --request APR-N --choice approve [--authorization r.json] [--ack ...]` | Registra a sua decisão (abre o prompt nativo) |
| `agents [--activate] [--roles a,b]` | Lista ou ativa Agent Contracts (decisão do usuário) |
| `settings [--apply]` | Mostra ou grava as regras nativas de segunda camada |
| `waves [--feature F] [--json]` | Calcula as ondas de tarefas paralelizáveis |
| `next [--feature F] [--json]` | Próximas ações do modo contínuo e critério de parada |
| `dispatch [--feature F] [--dry-run]` | Despacha a onda numa chamada: prompt, modelo e effort de cada agente e os `delegation` registrados |
| `validate-wave [--feature F] [--dry-run]` | `precheck` de cada tarefa executada, reprovação imediata de quem falha e um único validador para o resto |
| `precheck --task T [--json]` | Checagem determinística, sem modelo e sem rodar comandos: relatório, critérios com evidência, TDD, escopo e tokens de design |
| `mode [--set ask\|exec]` | Mostra ou troca o modo da sessão (trocar abre o prompt nativo) |
| `verify` / `status` | Integridade do log (cadeia, assinaturas, head externo) / resumo |
| `rotate-key` / `anchor` | Gira a chave de assinatura / grava uma âncora do log em `~/.aisef/anchors/` |

## `aisef_new.py`: contratos a partir de briefs

| Comando | Para quê |
|---|---|
| `example feature` / `example blueprint` | Mostra o formato do brief |
| `feature --brief b.json` | Gera Feature Contract, Task Contracts, RTM e o pedido de plano |
| `blueprint --brief b.json` | Gera o Engineering Blueprint |
| `quick --title ... --why ... [--path ...] [--test-cmd ...]` | Tarefa do caminho rápido (`FEAT-MAINT`) |

## Outros

| Comando | Para quê |
|---|---|
| `aisef_context.py pack --task T` | Pacote de contexto da tarefa (obrigatório, referenciado, sob demanda) |
| `aisef_context.py remember --summary ... --source-kind ... --source-ref ...` | Grava memória de projeto com fonte |
| `aisef_learn.py propose` / `accept` / `update` / `list` | Lições a partir de erros rotulados: propõe grupos, vira lição só com a sua aprovação e recalcula a confiança |
| `aisef_route.py --task T [--attempt N] [--validator --executor-level L3]` | Modelo e effort da tarefa ou do validador |
| `design_check.py validate` / `scan` / `shots` | Autoridade de design: tokens válidos, nada fora deles no código de UI, capturas em 375/768/1440 px |
| `check_project.py --project .` | Todas as [regras de consistência](check-rules.md) (é o que o `aisef-check` roda) |
| `build_panel.py --project .aisef --out .aisef/panel --with-page` | Gera o painel estático |
| `build_panel.py --project .aisef --out .aisef/panel --serve [--port 8765] [--open]` | Painel ao vivo em 127.0.0.1, regenerado quando `.aisef/` muda |
| `make_demo_project.py <pasta>` | Projeto de demonstração completo |

## Ferramentas do repositório (`tools/`)

| Comando | Para quê |
|---|---|
| `gen_agents.py [--check]` | Gera `agents/*.md` a partir da fonte única |
| `gen_docs.py [--check]` | Gera `docs/reference/check-rules.md` |
| `bench_hooks.py [--runs N] [--json]` | Mede a latência dos hooks |
