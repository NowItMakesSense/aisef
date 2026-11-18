# ADR 0017: Aprendizado contínuo revisado

- **Status:** aceito
- **Data:** 2026-11-18

## Contexto

O usuário pediu memória e aprendizado no nível do everything-claude-code (ECC). No código do ECC (`continuous-learning-v2`), um hook grava cada chamada de ferramenta, e um daemon chama o Haiku a cada 5 minutos para escrever "instincts" que entram na sessão seguinte. As falhas verificadas no código:
- a atualização e o decaimento da confiança estão só na documentação;
- a análise vem desligada no Windows, e o daemon não sobrevive lá;
- não há revisão humana antes de o texto entrar no contexto;
- o `/evolve` grava numa pasta que o Claude Code não lê;
- ignora subagentes;
- guarda tudo fora do repositório.

## Decisão

- **Sinais:** só **erros já rotulados** que o AISEF registra (reprovações, `precheck`, bloqueios do gateway, `scope_discovery`, correções, problemas de relatórios). Sem hook novo e sem daemon.
- **`aisef_learn.py propose`:** agrupa os sinais sem modelo. O orquestrador redige gatilho e ação.
- **`accept`:** é decisão do usuário (o gateway abre o prompt nativo) e grava evidência (ids do log), confiança inicial e revisão.
- **`update`:** recalcula a confiança em código testado (+0,05 em sucesso, −0,10 em reprovação, −0,02 por semana sem uso) e aposenta abaixo de 0,2.
- **Uso:** a lição entra só no pacote da tarefa relevante, com confiança ≥ 0,5, como referência. O `dispatch` registra quem recebeu o quê.
- **Contexto:** o doctor reinjeta o estado depois de `/compact` e `/resume`. O `PreCompact` não serve para isso, porque não injeta contexto.
- **Perfis de hook do ECC (minimal/standard/strict): descartados.** No AISEF, o gateway é o controle e precisa rodar sempre. O ganho de velocidade veio de juntar processos e da auditoria assíncrona.

## Consequências

O aprendizado funciona no Windows, é auditável e é compartilhado pelo time. Ele depende de o usuário revisar as propostas nos marcos: sem isso, nada é aprendido, e é de propósito.
