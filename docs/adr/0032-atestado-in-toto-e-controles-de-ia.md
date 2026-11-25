# ADR 0032: Atestado in-toto por tarefa e controles de IA no pacote de evidência

- **Status:** aceito
- **Data:** 2026-11-25

## Contexto

O pacote de evidência (T-02) se verifica sozinho, mas tem formato próprio. Ferramentas de cadeia de suprimentos
(SLSA, Sigstore, in-toto) e auditores que usam esse ecossistema esperam um atestado padrão: o que foi produzido
(subject), por qual processo (predicate), assinado. A tabela de controles cobria SOC 2 e ISO 27001, mas não os
marcos de governança de IA que os clientes já pedem: ISO/IEC 42001, EU AI Act e NIST AI RMF.

## Decisão

- `aisef_evidence.py build --in-toto` grava `attestations/<TASK>.intoto.json` para cada tarefa da feature. Cada
  arquivo é um envelope DSSE com um in-toto Statement v1:
  - **subject:** os arquivos que o relatório diz ter criado ou alterado, com o sha256 de hoje, e o commit
    (`gitCommit`). Arquivo que não existe mais vai para `predicate.files_missing`, não para o subject.
  - **predicate** (`https://aisef.dev/attestation/task/v0.1`): contrato (id, versão, sha256 canônico), agente,
    modelo e effort (`execution_profile`), ferramentas usadas (eventos `tool_used`), testes, TDD, validação (quem
    validou e o hash do evento) e quantos eventos do log são da tarefa.
- A assinatura é Ed25519 sobre o PAE do DSSE, com a chave do projeto (arquivo ou cofre, E-02). O `keyid` é o id da
  chave pública que já vai em `keys/`. Sem a chave privada, `--in-toto` recusa; não sai atestado sem assinatura.
- `aisef_evidence.py verify` confere cada envelope com as chaves públicas do pacote e confere que o sha256 do Task
  Contract no pacote é o do atestado.
- A tabela de controles ganha ISO/IEC 42001:2023 (A.6.2.8, A.6.2.4, A.9.2, A.4.4), EU AI Act art. 12(1) e 12(2) e
  NIST AI RMF 1.0 (Govern, Map, Measure, Manage). O status é calculado a partir do mesmo material dos outros
  controles.

## Limites

- O mapeamento é indicativo, para apoiar a auditoria. Não é certificação. O art. 12 do EU AI Act obriga o
  fornecedor de sistema de IA de alto risco; aqui ele é aplicado ao uso de agentes no desenvolvimento, como boa
  prática.
- O digest dos arquivos é o do momento em que o pacote é montado, não o do instante da entrega. O commit no subject
  amarra os dois quando o pacote é montado no commit da entrega.
- Atestado só por tarefa. Um atestado por feature (resumo) pode vir depois.

## Alternativas

- **Assinar com Sigstore (keyless, Fulcio + Rekor):** depende de rede e de identidade OIDC. A chave do projeto já
  existe e já assina o log.
- **Predicate SLSA Provenance:** descreve build, não desenvolvimento assistido por agente. Um predicate próprio diz
  o que importa aqui: contrato, agente, validação.

## Consequências

- O pacote pode ser lido por ferramentas in-toto. Basta registrar a chave pública do pacote como chave de
  verificação.
- `controls.json` cresce de 4 para 14 controles; consumidores que filtram por `framework` não quebram.
