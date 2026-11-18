# Spec e fatias verticais (método)

Adaptado das skills `grill-me`, `to-spec`, `to-tickets`, `tdd` e `implement-spec` de Matt Pocock ([mattpocock/skills](https://github.com/mattpocock/skills), MIT). O AISEF grava o resultado em `.aisef/` com rastreabilidade, em vez de publicar no issue tracker.

## Grill
- Uma pergunta por vez, sempre com a sua recomendação e o porquê.
- Investigue antes de perguntar: se o código ou os docs respondem, não pergunte.
- Feche cada ramo (comportamento, exceção, limite, o que fica fora) antes de abrir o próximo.
- Termos novos do domínio vão para o `GLOSSARY.md`; decisões difíceis de reverter viram ADR (com aprovação).

## Spec

| Campo | O que é |
|---|---|
| `problem` (Feature Contract) | O problema, do ponto de vista do usuário |
| `spec.solution` | A solução, em uma ou duas frases |
| `spec.user_stories` | Lista longa e numerada; cada uma no formato "Como <quem>, quero <o quê>, para <por quê>" |
| `spec.implementation_decisions` | Módulos, interfaces, contratos de API, decisões de schema. **Sem caminhos de arquivo nem trechos de código** (ficam velhos rápido) |
| `spec.testing_decisions` | O que é um bom teste aqui, que comportamento testar, exemplos parecidos no código |
| `spec.test_seams` | Interfaces públicas onde os testes atuam. Prefira as existentes e as mais altas; **o ideal é uma**. Confirme com o usuário |
| `scope.excluded` | Fora do escopo, explícito |

## Fatias verticais (tracer bullets)

```
Horizontal (evite)               Vertical (faça)
T1: tabela + migration           S1: pedir redefinição → e-mail com link (dados+API+e-mail)
T2: endpoints da API             S2: redefinir com link válido (UI+API+domínio)
T3: tela                         S3: link expirado ou usado é recusado (API+domínio)
nada funciona antes de T3        cada fatia funciona e é demonstrável sozinha
```

- A primeira fatia é o caminho mais fino de ponta a ponta. As seguintes engrossam o caminho.
- Cada fatia: demonstrável sozinha, cabe numa janela de contexto e tem ao menos um critério com teste automatizado num seam da spec.
- `depends_on` são as blocking edges. O trabalho sempre anda pela fronteira: as fatias cujos bloqueios já terminaram.
- Refatoração que facilita a feature vem antes, como fatia própria ("make the change easy, then make the easy change").
- Refatoração ampla (renomear um conceito em todo o código) usa expand-contract: introduzir o novo, migrar os usos, remover o antigo.

## TDD (o que o `implementer` faz e o `aisef-check` confere)
1. Escrever **um** teste para **um** comportamento, num seam aprovado, pela interface pública.
2. Rodar e ver **falhar** pelo motivo certo (vermelho).
3. Escrever o mínimo para passar e rodar (verde).
4. Repetir. Refatorar só no verde.

Anti-padrões: testar detalhe de implementação, teste tautológico (que passa sempre), mock do que você mesmo escreveu e fatiar os testes horizontalmente (todos os testes primeiro, todo o código depois).

Cada ciclo vai para `tdd_evidence.cycles` no Execution Report, com as duas execuções (comando, exit code, horário). O `aisef-check` recusa:
- vermelho que passou (`TDD-RED-NOT-FAILING`);
- verde que falhou (`TDD-GREEN-FAILING`);
- vermelho depois do verde (`TDD-RED-BEFORE-GREEN`);
- tarefa com TDD obrigatório sem evidência (`TDD-EVIDENCE-MISSING`).

## Correspondência com os comandos do Matt

| Você digita | No AISEF |
|---|---|
| `/grill-me`, `/grill-with-docs` | Fase Grill da `aisef-feature` (skills `grilling` e `domain-modeling`) |
| `/to-spec` | Fase Spec |
| `/to-tickets` | Fase Fatias (`aisef_new.py feature`) |
| `/implement-spec`, `/implement` | Modo contínuo da skill `aisef` com o agente `implementer` |
| `/tdd` | Regras de TDD do `implementer` (skill `tdd` pré-carregada) |
| `/code-review` | Revisão da feature antes do aceite |
