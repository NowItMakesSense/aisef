# ADR 0031: Chave privada do log no cofre do sistema

- **Status:** aceito
- **Data:** 2026-11-25

## Contexto

A chave Ed25519 que assina o log fica em `~/.aisef/keys/<projeto>/<chave>.pem`, sem senha, com permissão 600 (que
o Windows ignora). Qualquer coisa que copie a pasta do usuário leva a chave junto: backup, sincronização de nuvem,
disco copiado, outra conta com acesso ao disco. Com a chave, dá para reescrever o log e reassinar.

## Decisão

- `audit.key_store` no `.aisef/config.json`: `"file"` (padrão, o comportamento de antes) ou `"os"`.
- Com `"os"`, a chave vai para o cofre do sistema, e no lugar do PEM fica um marcador `<chave>.pem.os` sem segredo
  legível:
  - **Windows:** DPAPI (`CryptProtectData` por `ctypes`, sem dependência nova). O marcador guarda o blob cifrado, que
    só abre na mesma conta do Windows. A entropia amarra o blob ao projeto e à chave.
  - **macOS:** Keychain, pelo comando `security`; o segredo vai pelo stdin de `security -i`, nunca na linha de
    comando.
  - **Linux:** Secret Service (gnome-keyring, KWallet), pelo `secret-tool`, com o segredo pelo stdin.
- `core/aisef_keystore.py` é o único caminho de leitura e escrita da chave: assinatura do log, `init`, rotação de
  chave e chave de cada pessoa no log por pessoa.
- Migração: `aisef_migrate.py --key-store os|file` mostra o plano; com `--apply` (decisão do usuário) grava o config,
  move cada chave e registra um `decision_recorded`. A chave só sai da origem depois de lida de volta igual do
  destino.
- `audit.key_store = os` num sistema sem cofre utilizável é erro alto. A chave não cai para arquivo em silêncio. O
  doctor avisa quando o cofre não responde.
- O CI roda o teste com o cofre de verdade em Linux (gnome-keyring numa sessão D-Bus), macOS (keychain temporário) e
  Windows (DPAPI). Ali, cofre ausente é falha, não teste pulado.

## Limites (honestos)

- **Não protege contra código rodando na sessão do usuário.** Um processo do mesmo usuário pede a chave ao cofre como
  o AISEF pede. O cofre protege contra cópia de arquivo, não contra um processo malicioso local.
- Ao mover para o cofre, o PEM é apagado, mas sem garantia de apagamento físico (SSD, snapshots, backups antigos).
  Quem teme uma cópia antiga deve rodar a rotação de chave depois de migrar.
- Chave no DPAPI não muda de máquina. Para trocar de máquina, volte para `file`, copie e migre de novo lá, ou gere
  chave nova.
- O padrão continua `file`, porque projeto novo não pode depender de um chaveiro estar rodando (servidor Linux sem
  sessão gráfica, contêiner).

## Alternativas

- **PEM cifrado com senha:** exige a senha a cada evento, e os hooks não têm onde pedi-la.
- **Biblioteca `keyring`:** dependência nova, contra a regra de só usar `cryptography` e `jsonschema`. Os três cofres
  cabem em menos de 300 linhas.
- **Chave em hardware (TPM, Secure Enclave, YubiKey):** mais forte, mas Ed25519 não é suportado em todos. Fica para
  depois.

## Consequências

- Quem liga `os` ganha proteção contra o vazamento mais comum (cópia da pasta) sem mudar nada no fluxo.
- Mais um ponto de falha: cofre travado ou bloqueado impede o log de registrar, e o doctor avisa.
