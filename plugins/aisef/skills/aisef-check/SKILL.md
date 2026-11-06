---
name: aisef-check
description: 'Valida um projeto AISEF - cada documento contra seu JSON Schema, consistencia cruzada (mais de 60 regras de rastreabilidade, dependencias, agentes, permissoes, estado x evidencia, relatorios, aprovacoes, blueprint) e integridade do log de auditoria (cadeia de hash, assinaturas Ed25519, head externo). Use antes de qualquer transicao de estado, antes de pedir aprovacao, ao retomar trabalho, ou quando o usuario pedir "validar", "checar consistencia", "verificar auditoria".'
---

# aisef-check

CORE = `<skill-dir>/../../core`. Rode da raiz do projeto (Python com `jsonschema` e `cryptography`; use `$AISEF_PYTHON` se definido):

```
python -I CORE/check_project.py --project .aisef --policy CORE/permission-policy.v0.1.json --defaults CORE/orchestration-defaults.v0.1.json
python -I CORE/aisef_project.py verify --project .
```

- `check_project.py` sai com codigo 1 se houver erro; `--strict` trata avisos como erro; `--json <arquivo>` grava o relatorio estruturado.
- `aisef_project.py verify` compara o log com o head assinado **externo** (`~/.aisef/heads/`), o que detecta truncamento e reescrita.

## Como reportar
- Liste cada erro com o codigo da regra (ex.: `RTM-*`, `AUTH-*`, `BP-*`) e o arquivo, e diga o que corrigir.
- **Erro bloqueia** a transicao de estado (tarefa para `completed`, feature para aceite). Aviso nao bloqueia, mas mencione.
- Integridade comprometida: **pare**, mostre o erro ao usuario e nao tente "consertar" o log; correcoes sao eventos novos (`correction`), nunca edicao.
- Nunca diga que passou sem ter rodado e lido a saida.

## Manutencao do log (so com OK do usuario)
- O log cria sozinho um checkpoint assinado a cada 500 eventos (com ancora externa em `~/.aisef/anchors/`) e arquiva segmentos grandes em `.aisef/audit/archive/`; a cadeia continua entre eles. Limites em `config.json` -> `audit`.
- `python -I CORE/aisef_project.py anchor --project .`: ancora o ponto atual agora (antes de uma entrega, por exemplo).
- `python -I CORE/aisef_project.py rotate-key --project .`: troca a chave de assinatura; a antiga e apagada e qualquer evento novo assinado por ela vira erro. Use se a chave pode ter vazado ou periodicamente.

Para verificar se a politica e os schemas do plugin estao coerentes entre si (manutencao do plugin):
```
python -I CORE/check_policy_consistency.py CORE/permission-policy.v0.1.json CORE/authorization.schema.v0.1.json CORE/approval-request.schema.v0.1.json
```
