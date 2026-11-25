# ADR 0028: Dependência nova pergunta; a conferência na rede é opt-in

- **Status:** aceito
- **Data:** 2026-11-25
- **Ajusta:** [ADR 0027](0027-gateway-e-camada-o-sandbox-e-a-fronteira.md)

## Contexto

`npm install X` e `pip install X` passavam direto pelo gateway. Instalar um pacote roda código dele na máquina (scripts
de instalação, `setup.py`), e modelos inventam nomes de pacote com frequência: quem registra o nome inventado
(slopsquatting) ou um nome parecido com um conhecido (typosquatting) ganha execução de código no projeto.

## Decisão

- Comando que adiciona pacote novo (`pip`/`uv`/`poetry`/`pdm`, `npm`/`pnpm`/`yarn`/`bun`, `cargo add`, `go get`,
  `dotnet add package`, `gem install`, `composer require`) vira pergunta. Instalar o que já está declarado (`npm ci`,
  `npm install` sem nome, `pip install -r`, `pip install -e .`, `uv sync`, caminho local) segue livre.
- `aisef_deps.py check <ecossistema> <pacote>` confere três fontes públicas: o registro do ecossistema (existe?), a
  data da primeira publicação (menos de 30 dias é sinal de alerta) e o OSV (avisos de vulnerabilidade e `MAL-*`).
- Sem rede por padrão: o motivo da pergunta só sugere o comando. Com `"dependency_check": "online"` no
  `.aisef/config.json`, o gateway confere sozinho (até 3 pacotes por comando, 3 segundos por consulta) e põe o
  resultado no motivo. Falha de rede vira "não conferido", nunca liberação.
- Nada é negado: o usuário pode querer o pacote. A pergunta e o resultado ajudam a decidir.

## Consequências

Adicionar dependência sempre pede um clique. Em `bypassPermissions` é negado, como toda operação que exige aprovação.
O leitor não cobre gerenciadores raros (`conda`, `pipx`, `deno add`) nem `go install`; o sandbox segue sendo a
fronteira para o que o pacote faz depois de instalado.
