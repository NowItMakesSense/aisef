---
name: aisef-design
description: 'Define e mantem a autoridade de design de um projeto AISEF com interface - tipografia (familias e escala), paleta, espacamento, raio, movimento, componentes e regras de direcao de arte em .aisef/design/ - usando UI/UX Pro Max, Taste e Impeccable como fontes, aprovada como decisao arquitetural e conferida no codigo pelo design_check. Use quando o projeto tiver UI e ainda nao houver design aprovado, quando o usuario pedir "design system", "tipografia", "paleta", "deixar a interface melhor/consistente/menos generica", ou quando o aisef-check acusar DESIGN-MISSING.'
---

# aisef-design

CORE = `<skill-dir>/../../core`. Uma autoridade de design por projeto. Ela é decidida uma vez, aprovada por você e só muda por nova decisão. Dentro dela trabalham o agente `frontend` e as skills de design. **Sem isso, três skills de design juntas dão três tipografias e duas paletas, e cada fatia sai diferente.**

## 1. Antes de propor, investigue
- Se o projeto já tem design (CSS variables, tema do Tailwind, tokens do Figma, componentes), **extraia, não invente**: `sources` inclui `existing-codebase`.
- Identifique o `kind`: `product_app`, `dashboard`, `marketing_site` ou `mixed`. Ele decide quais skills entram.
- Veja quais skills de design estão instaladas (`.claude/skills/`, `claude plugin list --json`). Para instalar uma, use a **aisef-tooling** (com aprovação).

## 2. Fontes (cada uma no seu papel)

| Skill | Papel aqui | Quando |
|---|---|---|
| **UI/UX Pro Max** (`nextlevelbuilder/ui-ux-pro-max-skill`) | **Dados:** pares de fontes, paletas por setor, diretrizes de UX por stack. O script de busca só usa a stdlib, sem rede | Sempre que houver UI |
| **Taste** (`design-taste-frontend`) | **Direção de arte** anti-genérico: composição, tipografia expressiva, fotos reais | Só `marketing_site` ou `mixed`. É pesada (manda ler várias referências) e tem Stop hook de até 600 s |
| **Impeccable** (`pbakaus/impeccable`) | **Execução e conferência:** `typeset`, `layout`, `audit`, `polish`, `critique` e o detector determinístico (`npx impeccable detect`) | Sempre que houver UI. **Nunca** o modo `live` (pode abrir o Claude sem permissões; o gateway pede aprovação e você deve recusar) |
| `frontend-design` (Anthropic) | Base geral | Quando nenhuma das outras estiver instalada |

Conflitos já conhecidos:
- **Movimento:** a Taste proíbe scroll-linked e o `overdrive` do Impeccable faz isso. Quem decide é o campo `motion` dos tokens.
- **Paleta:** a Taste veta violeta como cor de marca. Vale o que estiver nos tokens.

## 3. Proponha os tokens
Escreva `.aisef/design/tokens.json` (schema `CORE/design-tokens.schema.v0.1.json`):
- `typography`: `families` (papel → família) e `scale` (com pelo menos 3 passos);
- `colors` (hex);
- `spacing`;
- `radius`, `shadows`, `breakpoints`;
- `motion` (`level`, `scroll_linked`);
- `components` (o inventário);
- `rules` (frases curtas de direção de arte);
- `sources`.

O `status` começa como `proposed`. Escreva também `.aisef/design/DESIGN.md` para humanos: o porquê de cada escolha, exemplos de hierarquia, do e don't. Valide:
```
python -I CORE/design_check.py validate --project .
```
Mostre ao usuário, de forma visual sempre que possível: os pares de fonte aplicados a um título e um parágrafo, a paleta com contraste e a escala.

## 4. Aprovação (decisão do usuário)
Crie um pedido `architecture_decision` com pelo menos 2 opções (por exemplo, duas direções tipográficas) e a sua recomendação, e leve à **aisef-approve**. Aprovado:
- `status: "approved"`;
- `approval.request_id` com o id do pedido.

O `aisef-check` acusa `DESIGN-UNAPPROVED` se o status disser aprovado sem o pedido aprovado. Mudanças depois disso seguem o mesmo caminho: nova versão (`version` + 1) e nova decisão.

## 5. Como isso vale no dia a dia
- O pacote de contexto (`aisef_context.py pack`) de toda fatia que toca UI traz os tokens, as regras e o comando de conferência.
- O `aisef_new.py feature` acrescenta a cada fatia de UI o critério "UI sem cores nem fontes fora dos tokens", verificado por `design_check.py scan --task T-x`.
- O `frontend` (implementador ou revisor de UI) usa as skills de design dentro dos tokens e entrega a evidência visual:
  - capturas em 375, 768 e 1440 px:
    ```
    python -I CORE/design_check.py shots --url <url> --out .aisef/reports/shots/<T-ID>
    ```
  - `impeccable detect` sem erro;
  - acessibilidade conferida.
- Ao fim da feature, rode `critique` e `polish` do Impeccable, e o resultado entra no relatório final.
