---
description: Padroes de projeto recorrentes no AISEF
source: ECC rules/common/patterns.md (MIT), adaptado
---

# Padrões

- **Repositório** para isolar o domínio do armazenamento: interface do lado do domínio, implementação na infraestrutura; um por agregado ou entidade raiz.
- **Envelope de resposta de API consistente** (dados, erro padronizado com código, mensagem e detalhes; paginação explícita). Use o padrão de erro que o projeto já tem (ex.: Problem Details, RFC 9457).
- **Injeção de dependência pelo construtor**; nada de buscar dependência global no meio da regra de negócio.
- **Configuração** lida uma vez na inicialização e validada; o resto do código recebe valores, não lê variável de ambiente.
- **Esqueleto antes de detalhe:** num projeto novo, a primeira fatia atravessa todas as camadas com o mínimo (tracer bullet), para validar a arquitetura cedo.
