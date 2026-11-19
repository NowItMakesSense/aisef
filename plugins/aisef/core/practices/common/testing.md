---
description: Testes e TDD no AISEF
source: ECC rules/common/testing.md (MIT), adaptado ao TDD por fatia do AISEF
---

# Testes

- **TDD nas fatias:** um comportamento por vez — teste que falha pelo motivo certo, mínimo para passar, refatoração no verde. A evidência vermelho→verde vai no Execution Report (`tdd_evidence`).
- **Teste comportamento pela interface pública**, nos seams aprovados na spec. Nunca detalhe de implementação; nada de mock do próprio código.
- **Pirâmide:** muitos testes de unidade (domínio e regras), alguns de integração (banco, fila, API real em contêiner quando possível), poucos ponta a ponta (jornadas críticas).
- **Estrutura AAA** (arrange, act, assert) e um motivo de falha por teste. Nome descreve o comportamento: `cancela_pedido_pago_estorna_valor`.
- **Independência:** cada teste cria e limpa seus dados; nada depende de ordem, relógio real, rede externa ou `sleep`.
- **Cobertura** é consequência, não meta: alvo de referência 80% nas regras de negócio, sem teste vazio para inflar número. O que importa é cada critério de aceite ter teste que falharia se ele quebrasse.
- **Bug corrigido = teste de regressão** que reproduz o bug antes da correção.
- Teste instável (flaky) vai para quarentena com a causa registrada; não é ignorado em silêncio.
