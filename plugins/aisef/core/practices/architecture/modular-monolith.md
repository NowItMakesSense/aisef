---
description: Monolito modular
source: AISEF
---

# Monólito modular

**Ideia:** um único deploy, dividido em **módulos com fronteiras fortes** (idealmente um por contexto delimitado). É o padrão recomendado para começar — dá para extrair serviços depois, se for preciso.

- Cada módulo tem **API pública** (fachada, interfaces, eventos) e um **interior privado**. Outro módulo só usa a API pública.
- **Dados por módulo:** cada módulo é dono das suas tabelas (schema próprio quando possível); nada de join entre tabelas de módulos diferentes nem leitura direta da tabela alheia.
- Comunicação síncrona pela API pública ou assíncrona por eventos internos.
- Sem dependência circular entre módulos; módulo compartilhado (*shared kernel*) pequeno e estável.
- Teste de arquitetura (ArchUnit, NetArchTest, dependency-cruiser, import-linter) para garantir as fronteiras no CI.

## Sinais de problema
"Módulo" que é só pasta (todo mundo importa tudo); tabelas compartilhadas; um módulo `common`/`utils` que cresce sem parar.

## Quando não usar
Projeto pequeno de um domínio só (uma estrutura em camadas basta) ou quando times independentes realmente precisam de deploy e escala separados (aí, microsserviços — com o custo que vem junto).
