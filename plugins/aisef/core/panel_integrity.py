#!/usr/bin/env python3
"""AISEF painel: explica a integridade do log de auditoria (U-02).

O verificador (audit_chain, audit_signing, aisef_streams) devolve frases soltas ("evento 12 (EV-..): hash nao confere").
Aqui cada frase vira um achado com: o que aconteceu (titulo), como foi detectado, o evento afetado (sequencia,
quando foi registrado, por quem, o que dizia), o ultimo evento integro antes dele e o que fazer. Erros do mesmo evento
viram um achado so, com todos os motivos. Sem rede e sem modelo; so le o log ja carregado.
"""
import re

VERIFY_CMD = "python -I <CORE>/aisef_project.py verify --project ."

# (padrao no texto do verificador, codigo, titulo, como foi detectado)
EVENT_RULES = [
    (r"hash nao confere com o conteudo", "altered", "Evento alterado depois de gravado",
     "O conteúdo do evento não bate mais com o hash calculado quando ele foi gravado: o arquivo do log foi editado."),
    (r"prev_hash nao confere", "chain", "Elo da cadeia quebrado",
     "O evento não aponta para o hash do anterior: houve remoção, inserção ou troca de evento logo antes dele."),
    (r"sequencia .* esperada", "sequence", "Sequência fora de ordem",
     "A numeração pula ou se repete aqui: um evento sumiu, entrou depois ou mudou de lugar."),
    (r"assinatura invalida", "signature", "Assinatura não confere",
     "A assinatura Ed25519 não vale para este evento: ele foi reescrito sem a chave privada do projeto."),
    (r"sem assinatura", "unsigned", "Evento sem assinatura",
     "O evento entrou no log sem passar pelo AISEF (que assina todo evento)."),
    (r"key_id desconhecido", "key", "Assinado por chave desconhecida",
     "A chave que assinou este evento não está entre as chaves públicas do projeto (.aisef/keys)."),
    (r"algoritmo", "algorithm", "Algoritmo desconhecido",
     "O evento usa um algoritmo de hash ou assinatura que o AISEF não usa."),
    (r"genesis", "genesis", "Início do log adulterado",
     "O evento genesis precisa ser o primeiro e único: o começo do log foi trocado."),
]
GENERAL_RULES = [
    (r"^log truncado", "truncated", "O final do log foi cortado",
     "O head assinado aponta para um evento que não está mais no arquivo: eventos do fim foram apagados."),
    (r"^hash do ultimo evento nao confere com o head", "head-hash", "Último evento diferente do assinado",
     "O último evento do arquivo não é o que o head assinado registrou: ele foi alterado ou trocado."),
    (r"^evento da sequencia do head", "head-missing", "Evento do head ausente ou diferente",
     "O evento que o head assinado registrou sumiu ou mudou."),
    (r"^head: ", "head-signature", "Head com assinatura inválida",
     "O arquivo head.json, que guarda o fim do log assinado, foi alterado."),
    (r"^head pertence a outro log_id", "head-other", "Head de outro log",
     "O head.json é de outro projeto ou de outro log."),
    (r"^log vazio, mas existe head", "emptied", "Log esvaziado",
     "Existe head assinado, mas o arquivo do log está vazio: todos os eventos foram apagados."),
    (r"^log ilegivel", "unreadable", "Log ilegível", "O arquivo do log não pôde ser lido como JSON linha a linha."),
    (r"^head ilegivel", "unreadable", "Head ilegível", "O arquivo head.json não pôde ser lido."),
    (r"mistura mais de um log_id", "mixed", "Eventos de outro log misturados",
     "O arquivo tem eventos de mais de um log_id: trechos de outro log foram colados aqui."),
    (r"^head atrasado", "head-late", "Head um pouco atrás do log",
     "Há eventos depois do último head assinado. Cada um tem assinatura própria; é normal entre uma gravação e outra."),
    (r"^sem head assinado", "no-head", "Sem head assinado",
     "Sem o head, apagar eventos do fim do log não seria detectado."),
    (r"^sem chaves publicas", "no-keys", "Sem chaves públicas",
     "Sem .aisef/keys, só a cadeia de hash foi conferida; as assinaturas não."),
    (r"cryptography ausente", "no-crypto", "Assinaturas não conferidas",
     "A biblioteca cryptography não está instalada nesta máquina."),
    (r"^sem log de auditoria", "no-log", "Sem log de auditoria", "Não existe .aisef/audit/log.jsonl neste projeto."),
    (r"mascarados nas fontes", "redacted", "Segredos mascarados",
     "Trechos com aparência de segredo foram trocados por [REDACTED] antes de ir para o painel."),
]
ACTION = {
    "error": "Não confie nos dados do painel até investigar. Rode `%s` para ver os detalhes e compare o log com a "
             "cópia do Git (git log -p .aisef/audit/) para achar quando o arquivo mudou." % VERIFY_CMD,
    "warning": "Não indica adulteração; vale corrigir para a verificação ficar completa.",
}
SEQ_RE = re.compile(r"sequencia (-?\d+|None) esperada (\d+)")
EV_RE = re.compile(r"^(?:(?P<stream>[^:]+): )?evento (?P<i>\d+) \((?P<id>[^)]*)\): (?P<msg>.*)$")


def _event_info(log, i):
    if i is None or i < 0 or i >= len(log):
        return None
    ev = log[i]
    actor = ev.get("actor") or {}
    return {"seq": ev.get("sequence", i), "event_id": ev.get("event_id"), "at": ev.get("timestamp"),
            "event_type": ev.get("event_type"), "actor": actor.get("id") or actor.get("type"),
            "summary": (ev.get("summary") or "")[:160], "task_id": ev.get("task_id"), "feature_id": ev.get("feature_id")}


def _match(rules, msg):
    for pat, kind, title, how in rules:
        if re.search(pat, msg):
            return kind, title, how
    return None


def explain(log, errors, warnings):
    """Lista de achados, erros primeiro e na ordem do log. Cada achado tem level, kind, title, how, action, raw e,
    quando ha um evento afetado, event (o evento) e before (o ultimo integro antes dele)."""
    by_event, out = {}, []
    # um evento apagado (ou inserido) desloca a numeracao de todos os seguintes: cada trecho continuo com o mesmo
    # deslocamento vira um achado so, no primeiro evento do trecho
    shift = {}
    for raw in errors:
        m = EV_RE.match(raw)
        n = SEQ_RE.search(raw) if m else None
        if n and n.group(1) != "None":
            shift[(m.group("stream"), int(m.group("i")))] = int(n.group(1)) - int(n.group(2))
    for level, items in (("error", errors), ("warning", warnings)):
        for raw in items:
            m = EV_RE.match(raw)
            if m:
                i = int(m.group("i"))
                k = shift.get((m.group("stream"), i))
                if k is not None and SEQ_RE.search(raw) and shift.get((m.group("stream"), i - 1)) == k:
                    continue  # continuacao do mesmo deslocamento: ja contado no inicio do trecho
                hit = _match(EVENT_RULES, m.group("msg")) or ("other", "Problema no evento", m.group("msg"))
                if k and SEQ_RE.search(raw):
                    prev_seq = (log[i - 1].get("sequence") if 0 < i <= len(log) else None)
                    cur_seq = log[i].get("sequence") if i < len(log) else None
                    if k > 0:
                        hit = ("removed", "%d evento%s apagado%s" % (k, "" if k == 1 else "s", "" if k == 1 else "s"),
                               "A numeração pula de #%s para #%s: %s do arquivo, e os seguintes ficaram deslocados."
                               % (prev_seq, cur_seq, "o evento do meio foi apagado" if k == 1 else "os eventos do meio foram apagados"))
                    else:
                        hit = ("inserted", "Evento inserido ou repetido",
                               "A numeração volta de #%s para #%s: entrou um evento que não estava na cadeia." % (prev_seq, cur_seq))
                key = (m.group("stream"), i)
                f = by_event.get(key)
                if f is None:
                    f = by_event[key] = {"level": level, "kind": hit[0], "title": hit[1], "how": [], "raw": [],
                                         "action": ACTION[level], "event": _event_info(log, i) if not m.group("stream") else None,
                                         "before": _event_info(log, i - 1) if not m.group("stream") and i > 0 else None}
                    if m.group("stream"):
                        f["stream"] = m.group("stream")
                    out.append(f)
                if hit[2] not in f["how"]:
                    f["how"].append(hit[2])
                f["raw"].append(raw)
                continue
            hit = _match(GENERAL_RULES, raw) or ("other", raw[:80], "")
            f = {"level": level, "kind": hit[0], "title": hit[1], "how": [hit[2]] if hit[2] else [], "raw": [raw],
                 "action": ACTION[level]}
            if hit[0] in ("truncated", "head-hash") and log:
                f["event"] = _event_info(log, len(log) - 1)
                n = re.search(r"termina na sequencia (\d+), head assinado esta em (\d+)", raw)
                if n:
                    f["missing"] = int(n.group(2)) - int(n.group(1))
            out.append(f)
    out.sort(key=lambda f: (f["level"] != "error", (f.get("event") or {}).get("seq", 10 ** 9)))
    return out
