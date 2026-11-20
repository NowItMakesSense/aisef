# ADR 0025: Git por risco

- **Status:** aceito
- **Data:** 2026-11-20
- **Ajusta:** [ADR 0004](0004-matriz-de-permissoes.md), item Git

## Contexto

Pelo ADR 0004, todo commit e todo push pediam a própria aprovação, inclusive numa branch de feature que ninguém mais usa. Numa feature com várias fatias, isso virava dezenas de prompts iguais, e o usuário passava a aprovar sem ler. A decisão de trocar essa regra foi tomada na entrevista do plano 0.11–0.14 (§2: "commit livre em `feat/*`; push coberto pelo escopo da feature; `main`, merge, release e force ficam como estão").

## Decisão

- **`commit_feature`** (livre em dev e staging): `git commit` quando a branch atual é de feature (prefixo `git.branch_prefix`, padrão `feat/`, nunca `main`, `master`, `develop`, `release/*` nem a `base_branch`). `--amend` continua reescrita de histórico.
- **`local_staging`** (livre): `git add`, `git switch` e `git checkout -b`, que preparam o commit ou criam e trocam a branch local.
- **`git_feature_branch`** (escopo em dev e staging, reforçada em produção): push de uma branch de feature para a branch de mesmo nome. Coberto por uma autorização de escopo com `resource_filters.branches`, pedida junto com o plano da feature. Push para outra branch (`feat/x:main`), `--force`, `--tags`, `--all` e `--delete` seguem as regras antigas.
- **A branch vem do `.git/HEAD`**, lido sem subprocesso. Quando ela não é conhecida (HEAD solto, `cd` ou `git -C` no comando, fora de um repositório), vale a regra antiga, que é a mais restritiva.
- **Teto dos agentes:** quem tem `commit` no Agent Contract pode `commit_feature` e `local_staging`, então os contratos existentes continuam valendo. Push de feature fica com o orquestrador: agente sem `push` no teto é negado.
- **Check:** `AUTH-GIT-BRANCH` acusa escopo de push sem branches ou com uma branch que não é de feature.

## Consequências

- Menos prompts na execução de uma feature; `main`, merge, release, force e reescrita de histórico continuam pedindo a aprovação de antes.
- A segurança do push depende de a branch de feature não ser a de produção. Por isso as protegidas nunca contam como feature, mesmo com um prefixo mal configurado.
