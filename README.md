# AISEF

Engenharia de software assistida por IA, com **autonomia na execução, rigor na validação e controle humano nas decisões importantes**. O AISEF é um plugin do Claude Code que você instala uma vez e usa em qualquer projeto, novo ou já iniciado.

## O que vem no plugin

| Componente | O que faz |
|---|---|
| Skill `aisef` | Orquestrador do ciclo descoberta → Feature Contract → Blueprint → tarefas → execução → validação independente → aceite. |
| `aisef-init` | Cria `.aisef/` no projeto e o log de auditoria assinado, e ativa o gateway. |
| `aisef-discovery` | Investiga antes de perguntar e nunca inventa regra de negócio. Também faz a Impact Analysis. |
| `aisef-feature` | Feature Contract, Engineering Blueprint, Task Contracts e reabertura de features. |
| `aisef-approve` | Approval Center: só o usuário decide, e cada decisão fica auditada. |
| `aisef-check` | Valida os schemas, mais de 60 regras de consistência e a integridade do log. |
| `aisef-panel` | Painel HTML com features, tarefas, RTM, aprovações, decisões, riscos, linha do tempo e dependências. |
| 8 agentes | `backend`, `frontend`, `database`, `qa`, `security`, `devops`, `domain` e `validator`, todos sob as regras do Agent Contract. |
| Execution Gateway | Hook PreToolUse que aplica a política de permissões (detalhes abaixo). |
| Audit & Evidence | Hook PostToolUse que registra cada operação numa cadeia de hash com assinatura Ed25519. Ele nunca registra segredos nem o raciocínio do modelo. |

### Como o gateway decide

- **Git:** status, log e diff passam livres. Commit, push, merge e release abrem cada um o seu próprio prompt nativo de aprovação. Force push, reescrita de histórico e exclusão de branch exigem aprovação reforçada.
- **Arquivos sensíveis** (`.env`, chaves, credenciais): o acesso pede aprovação.
- **Banco de dados e deploy:** o ambiente alvo é desconhecido, então a política os trata como produção. Ficam bloqueados, salvo aprovação reforçada para a operação exata.
- **Config, CI e IaC:** escrever nesses arquivos exige uma autorização de escopo, ou então abre um prompt.
- **O próprio AISEF:** o log de auditoria do projeto não pode ser editado à mão.

A política completa está em [`plugins/aisef/core/permission-policy.v0.1.json`](plugins/aisef/core/permission-policy.v0.1.json). Exceções do projeto ficam em `.aisef/policy.local.json` e só podem endurecer a política.

## Instalação

Pré-requisitos:

- Claude Code.
- Python 3.10 ou mais novo, com `pip install jsonschema cryptography`.
- No Windows, o Git Bash, que o Claude Code já usa para rodar os hooks.

No Claude Code, rode:

```
/plugin marketplace add fcarvalhosanna/aisef
/plugin install aisef@aisef
```

Se o Python que tem `cryptography` não for o padrão do PATH, defina `AISEF_PYTHON` com o caminho do executável.

Para atualizar todos os projetos de uma vez, use `/plugin marketplace update aisef`.

## Uso

**Projeto novo ou existente:** abra o Claude Code na pasta e peça "iniciar o AISEF neste projeto" (ou rode `/aisef:aisef-init`).

- Num **projeto existente**, ele investiga o que já existe antes de propor qualquer coisa.
- Num **projeto novo**, ele conduz a descoberta.

Depois, peça a feature normalmente ("implementar login com JWT"), e a skill `aisef` conduz o ciclo:

1. Você aprova o plano, o blueprint e as decisões arquiteturais.
2. A execução segue sem interrupções dentro do escopo autorizado.
3. Cada entrega é validada por um agente diferente do que a executou.
4. A feature só fecha com o seu aceite.

O aceite **não** autoriza commit, push nem merge.

O estado de cada projeto fica em `.aisef/`, e você pode versioná-lo. A chave privada de auditoria e o head assinado ficam em `~/.aisef/`, fora do repositório.

## Limites conhecidos

- O gateway só atua **dentro do Claude Code**. Em outras ferramentas, as regras escritas no `AGENTS.md` são apenas orientação.
- A aprovação acontece no prompt nativo de permissão. Se você aprovar sem ler, nenhuma camada técnica protege isso. Por esse motivo, as operações de maior risco exigem aprovação reforçada registrada **antes** do prompt.
- A detecção de segredos é heurística. A garantia real é redigir antes de gravar.
- O painel carrega o Mermaid de um CDN. Sem internet, ele mostra o código do diagrama.

## Desenvolvimento

```
python -m venv .venv && .venv/Scripts/pip install jsonschema cryptography   # Windows
python run_tests.py
claude plugin validate plugins/aisef
```

As suítes cobrem os schemas, as mais de 60 regras do `check_project`, a cadeia de hash, a assinatura, a coerência entre política e schemas, o painel (renderizado no Chrome headless quando disponível) e o gateway.

Para entender o projeto:

- [`docs/aisef-context.md`](docs/aisef-context.md): visão original.
- [`docs/decisions.md`](docs/decisions.md): o que foi decidido.
- [`docs/pending.md`](docs/pending.md): o que falta.

## Licença

MIT
