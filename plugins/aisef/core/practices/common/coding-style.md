---
description: Estilo de codigo do AISEF (vale para toda linguagem; a regra da linguagem prevalece quando conflitar)
source: ECC rules/common/coding-style.md (MIT), adaptado
---

# Estilo de código

## Princípios
- **KISS:** a solução mais simples que funciona. Clareza vale mais que esperteza.
- **YAGNI:** nada de abstração antes do segundo uso real — nenhuma interface extraída de uma única implementação, nenhuma fábrica de um produto só, nenhuma opção de configuração para um valor que nunca muda. Exceção: fronteira deliberada da arquitetura (porta/repositório que isola o domínio) vale desde a primeira implementação.
- **DRY com juízo:** extraia quando a repetição é real e muda junto; duas coisas parecidas que mudam por motivos diferentes não são duplicação.
- **Imutabilidade por padrão:** prefira criar um valor novo a alterar o existente, principalmente em estado compartilhado. Mutação local e controlada é aceitável quando a linguagem ou o desempenho pedem.

## Organização
- Muitos arquivos pequenos e coesos (200–400 linhas típico; 800 é teto de manutenção). Organize por feature ou domínio, não por tipo técnico.
- Funções curtas (até ~50 linhas), com uma responsabilidade e poucos parâmetros (mais de 3–4 pede um objeto).
- Aninhamento até 3–4 níveis: use retorno antecipado e extraia funções.

## Nomes
- O nome diz o que a coisa guarda ou faz, sem precisar de comentário. Booleano lê como afirmação (`isActive`, `hasAccess`).
- Use os termos do domínio (glossário do projeto), não sinônimos inventados.
- Constantes nomeadas no lugar de números mágicos (limites, prazos, tamanhos). Números óbvios (0, 1, status HTTP) não precisam.

## Erros e entrada
- Trate erro explicitamente em cada nível; nunca engula erro em silêncio. Mensagem amigável na UI, contexto detalhado no log do servidor (sem segredo nem dado pessoal).
- Valide toda entrada externa na fronteira do sistema (usuário, API de terceiros, arquivo, fila), de preferência com schema. Falhe cedo e com mensagem clara.

## Comentários
- Comente o **porquê** (restrição, decisão, armadilha), não o **o quê**. Código comentado não fica no repositório.

## Antes de entregar
- [ ] nomes claros; funções e arquivos dentro dos limites; sem aninhamento profundo
- [ ] erros tratados; entrada validada na borda
- [ ] sem valor fixo que deveria ser configuração; sem log de depuração esquecido
