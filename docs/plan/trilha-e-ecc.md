# Trilha E: equipe, boas práticas e arquitetura (port do ECC)

> **Status:** implementada na 0.12.0, 2026-11-19. Decisões nos ADRs 0020, 0021 e 0022.
> **Congelamento:** o usuário decidiu quebrar o congelamento do plano [melhorias-0.11-0.14](melhorias-0.11-0.14.md) para esta trilha. O que precisa de avaliação ficou na seção 3, para tratar depois. As tarefas do plano antigo (F-*, L-*, T-*, D-*) seguem iguais, nas versões seguintes.

## 1. Pedido

1. Trazer do everything-claude-code (ECC, MIT) tudo o que faz sentido, não só a memória.
2. Uma equipe de agentes grande e detalhada: "tudo que o ECC tem", sem mudar o agente `frontend`.
3. Melhorar as boas práticas.
4. Detectar DDD, Clean Architecture e outros estilos, e recomendar melhorias.

## 2. Fases entregues

| Fase | O que | Onde |
|---|---|---|
| E0 | Catálogo de agentes como fonte única; enums de papel viram `pattern` + `AGENT-ROLE-UNKNOWN` | `core/agents/`, `core/aisef_catalog.py` |
| E1 | Detecção de stack, estilo e regra de dependência; recomendações; adoção só com `architecture_decision` | `core/aisef_detect.py`, `core/detect/`, `ARCH-*` |
| E2 | 33 boas práticas (comuns, arquitetura, linguagem) instaladas em `.claude/rules/aisef/`; estilo e práticas no `pack` | `core/practices/`, `core/aisef_practices.py` |
| E3 | 22 papéis base sempre ativos (planejamento, revisão geral, corretores, entrega, processo) | catálogo |
| E4 | 34 papéis por stack, por domínio e manuais (UI só relata) | catálogo |
| E5 | Revisores escolhidos em código, gate antes do validador, revisão dupla em risco alto | `core/aisef_review.py`, `validate-wave` |
| E6 | Proteção de config de qualidade, bloqueio de `--no-verify`, `verify-loop` | `hooks/gateway.py`, `core/aisef_verify.py` |
| E7 | `conversation-analyzer` nas lições; recuperação iterativa de contexto | skill `aisef` |
| E8 | ADRs, README, CHANGELOG, avisos de terceiros, versão | `docs/`, `THIRD_PARTY_NOTICES.md` |

### Do ECC que ficou de fora (e por quê)
- **Agentes fora da engenharia do projeto:** chief-of-staff, marketing, SEO, homelab, rede, bengali, opensource-*.
- **GAN harness:** o avaliador mexe na UI viva, e o usuário não quer mudar o frontend.
- **`loop-operator` e `tdd-guide`:** redundantes com o modo contínuo e com o `implementer`.
- **Continuous-learning v2:** ADR 0017. Em resumo, a versão do AISEF é revisada pelo usuário e funciona no Windows.
- **Hookify, perfis de hook, instalação em outras ferramentas, ecc2.**

## 3. Lista de avaliação (testes e impedimentos para depois)

### Resultados (2026-11-19)
- **A-01, medido.** Descrições dos agentes no contexto de toda sessão: de ~800 para **~4.700 tokens** (31 papéis `always`: ~2.600). O Claude Code só avisa acima de 15.000 tokens. Decisão do usuário na tabela abaixo.
- **A-03, medido e corrigido.** 10 repositórios públicos de arquitetura conhecida mais o deckloom:
  - **Acertos (9 de 10):** jasontaylordev/CleanArchitecture, ardalis/CleanArchitecture, kgrzybek/modular-monolith-with-ddd, Sairyss/domain-driven-hexagon, ddd-by-examples/library, dotnet/eShop, bxcodec/go-clean-arch, hackathon-starter (MVC), psf/requests (sem estilo, corretamente).
  - **Erro restante:** ContosoUniversity (fatias verticais via Razor Pages + MediatR) não é reconhecido.
  - **Violações:** antes 6 falsas; depois das correções, 0 falsas. Sobram 1 real (ardalis: `Domain/Order.cs` importa `Infrastructure.Data`) e 2 discutíveis (Sairyss: `application` importando `libs/api` e uma porta guardada em `database/`).
  - **Correções:** `Infrastructure/Domain` conta como infraestrutura; import do próprio projeto `.API` não é violação; arquivos `*.port.*`/`*.adapter.*` e `AggregateRoot`/`DomainEvent` contam como sinal; Clean em Go (`domain`, `repository`, `rest`); microsserviços como pastas irmãs `*.API`/`*-service` com manifest. Regressão em `test_detect.py`.
- **A-08, confirmado na prática** (`claude -p`, Haiku): o subagente recebe as regras sem `paths:` ao iniciar e as com `paths:` quando lê um arquivo que casa. O CLAUDE.md também chega (documentação oficial).
- **A-01, decidido: encurtar.** As descrições dos 56 papéis novos foram reescritas: ~4.700 → **~3.000 tokens** por sessão. As 10 originais (inclusive `frontend`) não mudaram.
- **A-04, testado** (US$ 0,41). `react-reviewer` e `a11y-architect` rodaram só para leitura em `features/conta` do frontend do deckloom (cópia, sem tocar no projeto):
  - **`react-reviewer`:** 3 achados MEDIUM reais (400 sem feedback, `refreshSession` que trava a navegação, `key` que descarta a escolha do usuário).
  - **`a11y-architect`:** 3 achados MEDIUM de WCAG 4.1.3 e 3.3.1, mais uma regra de negócio "PENDENTE" sem ADR.
  - **Nenhum dos dois** propôs mudar layout, cores, espaçamento ou tokens. O que dependia do design system ficou como "não verificável".
- **A-05, medido** (feat-slugify, Sonnet, 1 repetição; `docs/benchmarks/outcomes-2026-11-19.*`):

  | Braço | Testes escondidos | Custo | Tempo |
  |---|---|---|---|
  | plain | 7/7 | US$ 0,11 | 21 s |
  | aisef (3 revisores + validador) | 7/7 | US$ 1,48 | 329 s |
  | aisef-norev (só validador) | 7/7 | US$ 1,91 | 533 s |

  Com uma repetição, a variação entre execuções é maior que o custo dos revisores (o braço sem revisores saiu mais caro). Conclusão possível hoje: o custo dos revisores não aparece acima do ruído; o custo do AISEF inteiro é ~14× o do Claude puro numa tarefa pequena. Para separar, são precisas 3+ repetições (WSL).
  - **O benchmark achou 3 defeitos, já corrigidos:**
    1. Os revisores, sem Write, não gravavam o veredito. Agora `aisef_review.py record` grava.
    2. O orquestrador seguia para o validador sem os vereditos. A regra `VAL-REVIEW-MISSING` passou a acusar.
    3. O `claude -p` do harness encerrava com subagentes em segundo plano ainda rodando. O harness agora usa `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` e retoma a sessão até o `next` parar. **Isso também invalida o benchmark da 0.11 rodado antes desta correção.**
- **A-06, não mensurável com o benchmark atual.** As tarefas já chegam especificadas, então planner, architect e spec-miner nunca rodam. Seria preciso um benchmark de planejamento.
- **A-07, decidido: manter a trava.**
- **A-04, decidido:** `react-reviewer` e `vue-reviewer` ativados pela stack, `a11y-architect` por qualquer stack de UI; entram na revisao de tarefas de UI e so relatam. `react-build-resolver` segue manual.
- **A-06, decidido: manter Opus** no planner, architect, spec-miner e healthcare-reviewer.
- **A-05, medido com 3 repetições** (feat-slugify, Sonnet, Windows; `docs/benchmarks/outcomes-2026-11-19-3reps.*`):

  | Braço | Testes escondidos | Custo por execução | Mediana | Tempo (mediana) |
  |---|---|---|---|---|
  | plain | 3/3 com 7/7 | US$ 0,13 / 0,17 / 0,13 | US$ 0,13 | 26 s |
  | aisef (3 revisores) | 3/3 com 7/7 | US$ 1,65 / 1,46 / 1,49 | US$ 1,49 | 335 s |
  | aisef-norev | 3/3 com 7/7 | US$ 1,32 / 2,49 / 1,22 | US$ 1,32 | 333 s |

  - **Custo dos revisores:** cerca de +US$ 0,17 por fatia na mediana (+13%). Na média, o braço sem revisores saiu mais caro (US$ 1,68 contra US$ 1,53), por causa de uma execução fora da curva. Conclusão: o custo dos revisores é pequeno e fica dentro da variação. Eles ficam ligados.
  - **Os revisores rodaram de verdade** nas 3 execuções do braço aisef: 3 relatórios de revisão por execução, e a tarefa chegou a `completed`.
  - **O AISEF custa cerca de 11× o Claude puro** numa tarefa pequena, com o mesmo resultado nos testes escondidos. A tarefa é pequena demais para o processo mostrar ganho de qualidade; esse ganho precisa ser medido em tarefas maiores e no uso real (M-05 e F-10).
  - Uma rodada anterior falhou em silêncio (8 de 9 execuções com custo zero, provavelmente a CLI recusando sessões por um tempo). O harness agora grava a saída quando há falha e para depois de 3 falhas seguidas.
- **A-11, conferido.** Os 56 papéis portados têm `source`, as 33 práticas têm `source:` e o `THIRD_PARTY_NOTICES.md` traz a licença MIT íntegra.

| # | O que avaliar | Como | Decide |
|---|---|---|---|
| A-01 | **Custo de contexto dos 66 agentes.** Toda descrição de agente do plugin entra na ferramenta Agent em toda sessão. | Medir os tokens do system prompt com e sem a 0.12. Se pesar, encurtar as descrições ou separar os papéis de stack em plugins `aisef-pack-<stack>`. | usuário |
| A-02 | **CLI real com muitos agentes de plugin.** | Conferir que os 66 aparecem como `aisef:<id>` e que o `model`/`effort` do frontmatter vale. Somam-se as pendências antigas: hooks async, `skills:` com namespace, `agent: aisef:ask` em `context: fork`. | — |
| A-03 | **Precisão da detecção de arquitetura.** | Rodar `detect` em 5 a 10 repositórios reais de estilos conhecidos e anotar acertos, falsos positivos (DDD por nome de pasta) e violações reais versus ruído. | — |
| A-04 | **Agentes ligados ao front:** react/vue reviewer, a11y, react-build-resolver, GAN harness. | Ativar num projeto de UI e conferir que não pioram os layouts antes de recomendar. | usuário |
| A-05 | **Custo e latência dos revisores por fatia.** | `bench_outcomes.py` com e sem `review.reviewers` (pass@k, tokens por tarefa concluída). | usuário |
| A-06 | **Opus no planner, architect, spec-miner e healthcare-reviewer.** | Comparar com Sonnet nas mesmas tarefas; trocar o `level` no catálogo se não compensar. | usuário |
| A-07 | **Falsos positivos da proteção de config de qualidade** e se vale portar o `gateguard` fact-force. | Usar num projeto real; ver quantas tarefas legítimas mexem em `tsconfig` ou `eslint`. | — |
| A-08 | **As boas práticas chegam aos subagentes?** | Confirmar que `.claude/rules/aisef/` (com `paths:`) é carregado nos subagentes. Hoje o `pack` também lista os caminhos, como reforço. | — |
| A-09 | **Pendências da 0.11 (do usuário).** | Benchmark no WSL (`bench_outcomes.py --run --reps 1 --tasks feat-slugify`, depois `--reps 3 --model sonnet`) e baseline do M-05 no deckloom limpo. | usuário |
| A-10 | **Metas da seção 8 do plano antigo.** | Continuam valendo, agora medidas com a equipe nova (F-10). | usuário |
| A-11 | **Atribuição MIT.** | Revisão final de `THIRD_PARTY_NOTICES.md` e do campo `source` do catálogo. | — |
| A-12 | **Regra de dependência por regex.** | Comparar com uma ferramenta da stack (import-linter, dependency-cruiser, ArchUnit) num projeto real; decidir se o `verify-loop` deve chamá-la quando existir. | — |
