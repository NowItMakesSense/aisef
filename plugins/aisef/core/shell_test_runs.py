#!/usr/bin/env python3
"""AISEF: invocacoes de executor de teste dentro de um comando de shell (E-01b).

O hook de auditoria guarda so os primeiros 400 caracteres do comando. Quando o agente escreve o teste num heredoc e
roda o teste no mesmo comando (`cat > x.test.ts <<'EOF' ... EOF` e depois `pnpm exec vitest run x.test.ts`), a
execucao fica depois do corte e a conferencia de TDD (check_rules_4) nao a encontrava. Aqui saem do comando inteiro
so as invocacoes de teste, sem o corpo dos heredocs (que traz o arquivo, nao comandos), para irem ao log num campo
proprio, curto.
"""
import re

RUNNERS = re.compile(r"\b(vitest|jest|pytest|py\.test|mocha|ava|tap|playwright|cypress|rspec|phpunit|pest|unittest|nose2|"
                     r"go test|cargo test|cargo nextest|dotnet test|mvn(?:w)? (?:\S+ )*test|gradle(?:w)? (?:\S+ )*test|"
                     r"(?:npm|pnpm|yarn|bun)(?: run)? test|deno test|mix test|swift test|flutter test|ctest|run_tests\.py)\b")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
SEP = re.compile(r"\s*(?:&&|\|\||;|\n)\s*")
MAX_RUNS, MAX_LEN = 6, 240


def _strip_heredocs(cmd):
    """Tira o corpo de cada heredoc (da linha seguinte ao <<EOF ate a linha EOF)."""
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        tags = [m.group(2) for m in HEREDOC.finditer(line)]
        i += 1
        for tag in tags:
            while i < len(lines) and lines[i].strip() != tag:
                i += 1
            i += 1  # a linha do terminador
    return "\n".join(out)


def extract(cmd):
    """Lista curta das invocacoes de teste do comando, na ordem, sem o `cd <pasta> &&` e sem pipes de saida."""
    runs = []
    for seg in SEP.split(_strip_heredocs(cmd or "")):
        seg = seg.split("|")[0].strip()  # `vitest run x | tail -20`: o que importa e o executor
        if seg and RUNNERS.search(seg) and not seg.startswith(("cd ", "cat ", "echo ", "grep ", "sed ", "#")):
            seg = " ".join(seg.split())[:MAX_LEN]
            if seg not in runs:
                runs.append(seg)
        if len(runs) >= MAX_RUNS:
            break
    return runs
