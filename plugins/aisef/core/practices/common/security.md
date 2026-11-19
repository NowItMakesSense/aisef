---
description: Seguranca minima obrigatoria no AISEF
source: ECC rules/common/security.md (MIT), adaptado
---

# Segurança

Antes de entregar qualquer tarefa:
- [ ] nenhum segredo no código, em teste, em log ou em mensagem de erro (use variável de ambiente ou cofre)
- [ ] toda entrada externa validada na borda; consultas e comandos parametrizados (nada de montar SQL, shell ou HTML com string do usuário)
- [ ] autenticação e autorização no servidor em toda ação protegida, inclusive a checagem de dono do recurso (IDOR)
- [ ] saída escapada no contexto certo (HTML, atributo, URL, JS)
- [ ] dados pessoais só os necessários, com finalidade (LGPD)
- [ ] dependências novas checadas (vulnerabilidade conhecida, manutenção, nome parecido com pacote popular)
- [ ] limite de taxa em login e operações caras; tempo limite em toda chamada externa

Achou um problema de segurança no meio de outra tarefa: pare a parte afetada e reporte ao orquestrador (descoberta de escopo). O agente `security` revisa toda tarefa de risco alto ou com ameaça no blueprint. O AISEF nunca lê segredos nem conecta ao banco.
