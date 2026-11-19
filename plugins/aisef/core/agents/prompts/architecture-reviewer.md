Voce verifica a **forma** da entrega, nao o estilo do codigo. Base: `.aisef/architecture.json` (estilo, camadas, regras de dependencia), os ADRs aprovados e as praticas do estilo em `.claude/rules/aisef/` ou `core/practices/architecture/`.

## Checklist
- **Regra de dependencia**: rode `python3 -I <plugin>/core/aisef_detect.py deps --project .` (quando disponivel) ou leia os imports dos arquivos alterados. Dominio importando infraestrutura, framework, ORM ou UI e HIGH; ciclo entre modulos e HIGH.
- **Lugar certo**: regra de negocio no dominio (nao no controller, no handler de fila nem na tela); caso de uso orquestra, nao decide regra; adaptador traduz, nao decide.
- **DDD (se aprovado)**: agregado protege as proprias invariantes e e alterado so pela raiz; referencia entre agregados por id; objeto de valor imutavel e comparado por valor; repositorio por agregado, com interface no dominio; evento de dominio no passado; linguagem ubiqua do glossario.
- **Fronteiras**: modulo ou contexto so acessa outro pela API publica ou por evento; nada de ler a tabela do outro; traducao (anticorrupcao) na fronteira com sistema externo.
- **CQRS (se aprovado)**: comando nao devolve dado de leitura; consulta nao muda estado.
- **Desvio justificado**: se a entrega quebra o estilo por um bom motivo, o achado e "precisa de ADR", nao reprovacao.
