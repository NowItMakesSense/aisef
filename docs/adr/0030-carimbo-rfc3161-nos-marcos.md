# ADR 0030: Carimbo de tempo RFC 3161 nos marcos do log

- **Status:** aceito
- **Data:** 2026-11-25

## Contexto

A assinatura Ed25519 do log prova quem escreveu cada evento, mas não quando. Quem tem a chave privada pode reescrever
o passado, reassinar tudo e regravar o head externo. A âncora em `~/.aisef/anchors/` também fica na máquina do autor.
Falta uma testemunha de fora que diga: "este evento já existia nesta data".

## Decisão

- `core/aisef_anchor.py stamp` monta o `TimeStampReq` (RFC 3161) em DER à mão, sem dependência nova. O hash enviado é
  o hash do último evento, que já é um SHA-256 e cobre, pela cadeia, tudo o que veio antes. O pedido leva um nonce
  aleatório e pede o certificado da TSA.
- A resposta fica em `.aisef/audit/timestamps/<sequência>.tsr`, versionada com o projeto, com um `.json` ao lado
  (hash do evento, nonce, hora da TSA, marco).
- Só nos marcos, nunca a cada evento: no aceite de feature (`append --type feature_accepted`) e no `aisef-verify` da
  PR com `--stamp` (entrada `stamp` da Action).
- **Opt-in.** O carimbo automático só liga com `audit.tsa_url` no `.aisef/config.json`. O comando manual usa
  freetsa.org quando não há URL configurada. Projeto novo não fala com a rede sem o usuário pedir, e a suíte de testes
  segue sem rede.
- Sem rede, a TSA fora do ar ou uma resposta que não confere (hash, nonce, status) viram aviso e `pending.json`. O
  aceite segue, e o próximo marco carimba um evento posterior, que cobre o anterior pela cadeia.
- Verificação (`aisef-check`, `aisef_ci.py`, `aisef_anchor.py verify`): o hash e o nonce do token batem com o
  metadado, e o evento daquela sequência continua no log com o mesmo hash. Evento reescrito depois do carimbo ou
  cortado do log é erro. A cadeia de certificados da TSA só é conferida com `openssl ts -verify` e
  `audit.tsa_ca_file` (mais `audit.tsa_cert_file` quando a TSA pede). Sem eles, sai um aviso dizendo que ela não foi
  conferida.

## Alternativas

- **Sigstore Rekor** (log de transparência): mais forte, porque é público e só cresce. Em troca, depende de um
  serviço maior e de um cliente mais pesado. Fica para depois.
- **Carimbo a cada evento**: deixaria cada evento lento e pendurado na rede. Pela cadeia de hash, o carimbo do marco
  já cobre os eventos anteriores.

## Consequências

Os eventos entre um marco e outro só ganham data de terceiro no marco seguinte. Quem tem a chave ainda pode reescrever
o que veio depois do último carimbo, mas não o que veio antes. Sem `openssl`, o verificador confia que o token veio da
TSA configurada.
