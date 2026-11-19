"""Pacotes por stack (E4): revisores de linguagem, corretores de build, revisores de dominio e papeis ligados a UI.
Ativacao por stack detectada (`aisef_project.py detect`); os de dominio e os de UI sao `manual`.
Checklists adaptados do ECC (affaan-m/everything-claude-code, MIT), condensados para o AISEF."""

# id -> (nome, ativacao, comandos de diagnostico, foco da descricao, checklist [(severidade, item)])
REVIEWERS = {
    "python-reviewer": ("Python", "stack:python", "ruff check . ; mypy . (ou pyright) ; bandit -r . ; pip-audit ; pytest -q",
        "PEP 8, type hints, idiomas, seguranca e concorrencia",
        [("CRITICAL", "SQL com f-string ou `%`; `subprocess` com `shell=True` e entrada externa; `eval`/`exec`; `pickle`/`yaml.load` sem `SafeLoader` em dado externo; segredo no codigo"),
         ("CRITICAL", "`except:` ou `except Exception: pass` que engole erro; recurso sem `with`"),
         ("HIGH", "argumento padrao mutavel (`def f(x=[])`); funcao publica sem type hints onde o projeto tipa; `Any` desnecessario; `Optional` sem checagem"),
         ("HIGH", "chamada bloqueante (requests, `time.sleep`, I/O de arquivo) dentro de `async def`; estado global mutavel compartilhado entre threads"),
         ("MEDIUM", "laco que deveria ser compreensao ou `itertools`; `print` no lugar de `logging`; `datetime` sem fuso; caminho com `+` no lugar de `pathlib`")]),
    "django-reviewer": ("Django", "stack:django", "python manage.py check --deploy ; python manage.py makemigrations --check --dry-run ; pytest -q",
        "ORM, DRF, migrations e configuracao de seguranca",
        [("CRITICAL", "`raw()`/`extra()`/cursor com string montada; `DEBUG=True` ou `SECRET_KEY` no codigo; `csrf_exempt` sem motivo; `mark_safe` em dado do usuario"),
         ("HIGH", "N+1 (falta `select_related`/`prefetch_related`); operacao em varios modelos sem `transaction.atomic`; queryset avaliado em laco"),
         ("HIGH", "serializer DRF com `fields = '__all__'` expondo campo sensivel; view sem `permission_classes`; filtro por usuario ausente (IDOR)"),
         ("HIGH", "migration com `RunPython` sem funcao reversa; migration que altera dados e schema juntos em tabela grande"),
         ("MEDIUM", "regra de negocio na view (prefira servico ou modelo); signal usado para fluxo principal; `settings` lido fora da inicializacao")]),
    "fastapi-reviewer": ("FastAPI", "stack:fastapi", "ruff check . ; mypy . ; pytest -q",
        "async, injecao de dependencia, Pydantic, seguranca e OpenAPI",
        [("CRITICAL", "endpoint sem dependencia de autenticacao onde deveria; CORS `allow_origins=['*']` com credenciais; SQL montado com string"),
         ("HIGH", "chamada bloqueante (driver sincrono, `requests`) em `async def`; sessao de banco sem fechar (use dependencia com `yield`)"),
         ("HIGH", "resposta sem `response_model` vazando campo interno; modelo de entrada reutilizado como saida; validacao fora do Pydantic"),
         ("MEDIUM", "codigo de status errado; erro sem `HTTPException` padronizada; dependencias duplicadas em vez de `Depends` reutilizavel; OpenAPI sem descricao e exemplos")]),
    "typescript-reviewer": ("TypeScript e JavaScript", "stack:typescript|javascript", "npx tsc --noEmit ; npx eslint . ; npm test ; npm audit",
        "seguranca de tipos, async, seguranca Node/web e idiomas",
        [("CRITICAL", "`eval`/`new Function` com entrada externa; SQL ou comando montado com template string; `innerHTML`/`dangerouslySetInnerHTML` com dado do usuario; segredo no bundle do cliente"),
         ("HIGH", "`any` explicito ou implicito escapando para API publica; `as` forcando tipo sem checagem; `!` (non-null) sem garantia; `@ts-ignore` sem motivo"),
         ("HIGH", "promessa sem `await` nem `.catch`; `forEach` com `async`; `Promise.all` onde uma falha deveria ser tolerada (use `allSettled`)"),
         ("HIGH", "validacao de entrada externa ausente na borda (zod, valibot ou equivalente)"),
         ("MEDIUM", "`==` no lugar de `===`; mutacao de objeto recebido; enum onde uniao de literais basta; `console.log` esquecido")]),
    "go-reviewer": ("Go", "stack:go", "go vet ./... ; staticcheck ./... ; go test -race ./... ; govulncheck ./...",
        "Go idiomatico, concorrencia, tratamento de erro e desempenho",
        [("CRITICAL", "SQL montado com `fmt.Sprintf`; `exec.Command` com `sh -c` e entrada externa; segredo no codigo"),
         ("CRITICAL", "erro ignorado (`_ =` ou retorno nao checado) em I/O, banco ou rede"),
         ("HIGH", "goroutine sem forma de terminar (vazamento); acesso concorrente sem sincronizacao (rode `-race`); `context` ignorado ou nao propagado; canal sem dono claro"),
         ("HIGH", "erro sem contexto (use `fmt.Errorf(\"...: %w\", err)`); `panic` em codigo de biblioteca; comparacao de erro com `==` em vez de `errors.Is`/`As`"),
         ("MEDIUM", "interface grande ou definida do lado de quem implementa; ponteiro para slice ou map; `defer` em laco; alocacao em caminho quente")]),
    "rust-reviewer": ("Rust", "stack:rust", "cargo clippy -- -D warnings ; cargo test ; cargo audit",
        "ownership, lifetimes, tratamento de erro, unsafe e idiomas",
        [("CRITICAL", "`unsafe` sem comentario `SAFETY:` provando a invariante; FFI sem checagem de ponteiro nulo"),
         ("HIGH", "`unwrap`/`expect` em caminho de producao que pode falhar; `panic!` em biblioteca; erro sem contexto (`thiserror`/`anyhow` conforme o projeto)"),
         ("HIGH", "`clone` para fugir do borrow checker em caminho quente; `Rc<RefCell>` onde a posse e clara; lock segurado atraves de `.await`"),
         ("MEDIUM", "`String` onde `&str` basta; iterador convertido em `Vec` sem necessidade; `match` que deveria ser `if let`; API publica sem `#[must_use]` em resultado importante")]),
    "java-reviewer": ("Java (Spring Boot ou Quarkus)", "stack:java", "./mvnw -q verify (ou ./gradlew check) ; spotbugs/pmd quando configurados",
        "camadas, JPA, transacoes, seguranca e concorrencia; detecta Spring ou Quarkus",
        [("CRITICAL", "SQL/JPQL montado com concatenacao; endpoint sem regra de seguranca; segredo em `application.properties` versionado; deserializacao de tipo arbitrario"),
         ("HIGH", "N+1 do JPA (`FetchType.EAGER` ou falta de `JOIN FETCH`/entity graph); `@Transactional` em metodo privado ou chamado de dentro da propria classe (nao aplica)"),
         ("HIGH", "entidade JPA exposta direto na API (use DTO); `Optional.get()` sem checagem; excecao engolida; recurso sem try-with-resources"),
         ("HIGH", "estado mutavel em bean singleton; `synchronized` amplo demais; `@Async` sem executor configurado"),
         ("MEDIUM", "injecao por campo em vez de construtor; controller com regra de negocio; `null` retornado onde caberia `Optional` ou colecao vazia")]),
    "kotlin-reviewer": ("Kotlin e Android/KMP", "stack:kotlin", "./gradlew lint detekt test (conforme o projeto)",
        "idiomas, seguranca de coroutines, Compose e Clean Architecture no Android",
        [("CRITICAL", "segredo no codigo ou no `BuildConfig` versionado; WebView com JavaScript e entrada externa; SQL montado com string"),
         ("HIGH", "`!!` sem garantia; `GlobalScope`; coroutine sem escopo de ciclo de vida; `runBlocking` na main thread; excecao engolida em `catch` de coroutine"),
         ("HIGH", "Compose: estado sem `remember`/`rememberSaveable`; efeito colateral fora de `LaunchedEffect`; recomposicao cara (lambda instavel, lista sem `key`)"),
         ("MEDIUM", "`var` onde `val` basta; classe de dados mutavel; ViewModel acessando View ou Context; dominio dependendo de Android")]),
    "swift-reviewer": ("Swift", "stack:swift", "swift build ; swift test ; swiftlint (quando configurado)",
        "protocolos, semantica de valor, ARC, concorrencia e seguranca",
        [("CRITICAL", "segredo no codigo ou no Info.plist; Keychain ignorado para credencial; ATS desligado sem motivo"),
         ("HIGH", "force unwrap (`!`) ou `try!` em caminho de producao; ciclo de referencia (closure sem `[weak self]` onde o objeto guarda a closure)"),
         ("HIGH", "concorrencia: dado compartilhado fora de `actor`; atualizacao de UI fora do `@MainActor`; tipo nao `Sendable` cruzando fronteira de concorrencia"),
         ("MEDIUM", "classe onde `struct` basta; heranca onde protocolo basta; `Any` sem necessidade; erro silenciado com `try?` sem tratar")]),
    "csharp-reviewer": (".NET e C#", "stack:csharp", "dotnet build -warnaserror ; dotnet test ; dotnet list package --vulnerable",
        "convencoes .NET, async, nullable, seguranca e desempenho",
        [("CRITICAL", "SQL montado com interpolacao (use parametros ou EF); segredo em `appsettings.json` versionado; endpoint sem `[Authorize]` onde deveria"),
         ("HIGH", "`async void` fora de handler de evento; `.Result`/`.Wait()` (deadlock); `CancellationToken` nao propagado"),
         ("HIGH", "nullable desligado ou `!` sem garantia; `IDisposable` sem `using`; excecao engolida ou `catch (Exception)` generico"),
         ("MEDIUM", "consulta EF sem `AsNoTracking` em leitura; N+1 sem `Include`; servico com tempo de vida errado na injecao (scoped dentro de singleton)")]),
    "fsharp-reviewer": ("F#", "stack:fsharp", "dotnet build ; dotnet test",
        "idiomas funcionais, tipos, pattern matching e computation expressions",
        [("HIGH", "pattern matching incompleto (aviso FS0025 ignorado); excecao usada para fluxo normal (prefira `Result`)"),
         ("HIGH", "`mutable` e efeitos colaterais no nucleo; estado invalido representavel (use uniao discriminada)"),
         ("MEDIUM", "interop .NET com `null` sem `Option`; computation expression aninhada demais; ordem de arquivos no `.fsproj` escondendo dependencia circular")]),
    "cpp-reviewer": ("C++", "stack:cpp", "cmake --build build ; ctest ; clang-tidy ; sanitizers (ASan/UBSan) nos testes",
        "seguranca de memoria, C++ moderno, concorrencia e desempenho",
        [("CRITICAL", "buffer overflow, uso apos liberar, ponteiro pendurado; `strcpy`/`sprintf`/`gets`; aritmetica de ponteiro sem limite; comportamento indefinido"),
         ("HIGH", "`new`/`delete` manual (use RAII, `unique_ptr`, `make_unique`); copia cara onde move basta; excecao atravessando destrutor"),
         ("HIGH", "condicao de corrida; lock sem RAII (`lock_guard`/`scoped_lock`); ordem de lock inconsistente"),
         ("MEDIUM", "`#define` onde `constexpr` basta; cast estilo C; heranca sem destrutor virtual; header pesado sem necessidade")]),
    "php-reviewer": ("PHP e Laravel", "stack:php", "composer validate ; vendor/bin/phpstan analyse ; vendor/bin/phpunit (ou pest)",
        "PSR-12, tipos, Eloquent, seguranca e desempenho",
        [("CRITICAL", "SQL com interpolacao (`DB::raw` com entrada); mass assignment sem `$fillable`/`$guarded`; `{!! !!}` com dado do usuario; `unserialize` em dado externo"),
         ("HIGH", "N+1 do Eloquent (falta `with`); falta de `declare(strict_types=1)` onde o projeto usa; tipos de retorno ausentes"),
         ("HIGH", "validacao fora de Form Request; autorizacao sem Policy/Gate; operacao multipla sem transacao"),
         ("MEDIUM", "controller com regra de negocio; `env()` fora de arquivo de config; facade em codigo de dominio")]),
    "ruby-reviewer": ("Ruby e Rails", "stack:ruby", "bundle exec rubocop ; bundle exec brakeman ; bundle exec rspec (ou rails test)",
        "Ruby idiomatico, seguranca do Active Record e padroes do Rails",
        [("CRITICAL", "SQL com interpolacao em `where`/`find_by_sql`; `html_safe`/`raw` em dado do usuario; strong parameters ausentes; `send`/`constantize` com entrada externa"),
         ("HIGH", "N+1 (falta `includes`); callback com efeito externo (e-mail, API) dentro de transacao; `update_all`/`delete_all` pulando validacao sem querer"),
         ("HIGH", "migration irreversivel sem `down`; indice ausente em chave estrangeira"),
         ("MEDIUM", "regra de negocio no controller; `rescue => e` generico; metodo com muitos niveis de bloco")]),
    "flutter-reviewer": ("Flutter e Dart", "stack:flutter", "dart analyze ; flutter test",
        "widgets, gerenciamento de estado, idiomas Dart, desempenho e acessibilidade",
        [("CRITICAL", "segredo no codigo do app; armazenamento de credencial fora de armazenamento seguro"),
         ("HIGH", "`setState` depois de `dispose` (falta checar `mounted`); controller ou stream sem `dispose`; `BuildContext` usado apos `await`"),
         ("HIGH", "logica de negocio dentro do widget; estado global mutavel fora do padrao de estado escolhido no projeto"),
         ("MEDIUM", "falta de `const` em widget; `build` caro ou com efeito colateral; lista longa sem `ListView.builder`; `!` sem garantia")]),
    "gdscript-reviewer": ("GDScript e Godot 4", "stack:godot", "godot --headless --check-only (quando disponivel) ; testes GUT/gdUnit do projeto",
        "tipagem estatica, cena e nos, sinais, ciclo de vida e desempenho",
        [("HIGH", "acesso a no por caminho fragil (`get_node` com caminho longo) em vez de `@onready` ou export; no liberado e ainda referenciado"),
         ("HIGH", "sinal conectado sem desconectar ou duplicado; logica em `_process` que deveria ser evento"),
         ("MEDIUM", "variaveis sem tipo estatico onde o projeto tipa; alocacao por frame; `load` em tempo de execucao no lugar de `preload`")]),
    "react-reviewer": ("React", "manual", "npx tsc --noEmit ; npx eslint . (com regras de hooks) ; npm test",
        "hooks, desempenho de renderizacao, fronteira server/client e acessibilidade, sem opinar sobre o visual",
        [("CRITICAL", "`dangerouslySetInnerHTML` com dado do usuario; segredo exposto em componente cliente ou variavel publica"),
         ("HIGH", "regra dos hooks quebrada; dependencias de `useEffect`/`useMemo`/`useCallback` erradas; efeito sem limpeza; estado derivado guardado em estado"),
         ("HIGH", "fronteira server/client errada (Next.js): dado sensivel passado ao cliente; `use client` amplo demais"),
         ("MEDIUM", "lista sem `key` estavel; re-render em cascata por objeto ou funcao recriados; elemento interativo sem papel ou rotulo acessivel")]),
    "vue-reviewer": ("Vue", "manual", "npx vue-tsc --noEmit ; npx eslint . ; npm test",
        "Composition API, reatividade, arquitetura de componentes e seguranca, sem opinar sobre o visual",
        [("CRITICAL", "`v-html` com dado do usuario; segredo exposto no cliente"),
         ("HIGH", "reatividade perdida (desestruturar `reactive`, `props` sem `toRefs`); `watch` sem limpeza; mutacao de prop"),
         ("MEDIUM", "`v-for` sem `key` ou com `v-if` no mesmo elemento; logica pesada no template; store usado onde prop basta")]),
}

# id -> (nome, ativacao, comandos, correcoes tipicas)
RESOLVERS = {
    "build-error-resolver": ("TypeScript/JavaScript", "stack:typescript|javascript", "npx tsc --noEmit ; npm run build ; npm run lint",
        "tipo incompativel (corrija o tipo ou o dado, nao `any`); import ou caminho errado (confira `paths` e extensao ESM/CJS); dependencia ausente ou duplicada; versao de Node incompativel"),
    "python-build-resolver": ("Python", "stack:python", "python -m compileall -q . ; pip check ; mypy . ; pytest -q",
        "import quebrado ou circular; dependencia ausente no manifest; conflito de versao (`pip check`); erro de tipo do mypy (corrija o tipo, nao `type: ignore`)"),
    "django-build-resolver": ("Django", "stack:django", "python manage.py check ; python manage.py makemigrations --check ; pytest -q",
        "conflito de migrations (gere merge migration, nunca apague migration aplicada); app fora de `INSTALLED_APPS`; import circular entre apps; setting ausente"),
    "go-build-resolver": ("Go", "stack:go", "go build ./... ; go vet ./... ; go mod tidy",
        "import nao usado ou ausente; `go.mod` desatualizado (`go mod tidy`); interface nao satisfeita; ciclo de import (extraia o tipo comum)"),
    "rust-build-resolver": ("Rust", "stack:rust", "cargo check ; cargo clippy ; cargo build",
        "erro do borrow checker (reestruture o escopo antes de clonar); lifetime ausente; trait nao implementada; feature de crate desligada"),
    "java-build-resolver": ("Java (Maven/Gradle)", "stack:java", "./mvnw -q compile (ou ./gradlew compileJava) ; testes",
        "dependencia em conflito (veja a arvore de dependencias); versao do JDK; anotacao de processamento ausente (Lombok, MapStruct); bean nao encontrado no contexto Spring/Quarkus"),
    "kotlin-build-resolver": ("Kotlin/Gradle", "stack:kotlin", "./gradlew build",
        "versao do Kotlin e do plugin Gradle incompativeis; kapt/ksp; tipo nullable onde nao nullable e esperado; dependencia KMP no source set errado"),
    "swift-build-resolver": ("Swift/Xcode", "stack:swift", "swift build ; xcodebuild -scheme <esquema> build",
        "resolucao de pacote SPM; erro de concorrencia estrita (Sendable, isolamento de ator); assinatura e provisioning (reporte, nao altere credencial)"),
    "dart-build-resolver": ("Dart/Flutter", "stack:dart|flutter", "dart analyze ; flutter pub get ; flutter build",
        "conflito de versao no `pubspec.yaml`; null safety; codigo gerado desatualizado (`dart run build_runner build`); plugin nativo sem configuracao de plataforma"),
    "cpp-build-resolver": ("C++/CMake", "stack:cpp", "cmake -S . -B build ; cmake --build build",
        "simbolo indefinido no link (biblioteca ou ordem de link); header ausente; erro de template; flags de padrao C++ inconsistentes"),
    "pytorch-build-resolver": ("PyTorch", "stack:pytorch", "python -c 'import torch; print(torch.__version__, torch.cuda.is_available())' ; testes do projeto",
        "formato de tensor incompativel (imprima `shape` em cada passo); tensor em dispositivos diferentes; gradiente nao calculado (`requires_grad`, `no_grad`); falta de memoria (lote menor, acumulacao de gradiente)"),
    "harmonyos-app-resolver": ("HarmonyOS (ArkTS/ArkUI)", "stack:harmonyos", "hvigorw assembleHap (ou o build do projeto)",
        "gerenciamento de estado V2 (`@ComponentV2`, `@Local`, `@Param`) misturado com V1; API de ArkTS que nao existe na versao alvo; permissao ausente no `module.json5`"),
    "react-build-resolver": ("React (Vite, webpack, Next.js, CRA, Parcel, esbuild, Bun)", "manual", "npm run build ; npx tsc --noEmit",
        "JSX/TSX com tipo errado; import de modulo so de servidor no cliente; config do bundler; variavel de ambiente sem o prefixo publico exigido"),
}


def reviewer_prompt(lang, cmds, items):
    lines = ["Voce revisa codigo %s da entrega, dentro das convencoes do projeto. O code-reviewer cobre o geral: foque no que e especifico da linguagem e do framework." % lang,
             "", "## Diagnostico", "Rode o que o projeto tiver configurado: `%s`. Ferramenta ausente nao e achado; registre que nao rodou." % cmds,
             "", "## Checklist"]
    lines += ["- **%s**: %s." % (sev, txt) for sev, txt in items]
    return "\n".join(lines)


def resolver_prompt(lang, cmds, fixes, ui=False):
    lines = ["Voce faz o build %s voltar a passar com o **menor diff possivel**." % lang, "",
             "## Processo",
             "1. Rode o comando que falha (`%s`) e leia o **primeiro** erro; erros seguintes costumam ser consequencia." % cmds,
             "2. Ache a causa no codigo ou na configuracao, corrija so ela e rode de novo.",
             "3. Repita ate verde ou ate o limite de tentativas; registre cada rodada como evidencia.", "",
             "## Causas tipicas", "- " + "\n- ".join(f.strip() for f in fixes.split(";"))]
    if ui:
        lines += ["", "Nao altere componentes visuais, estilos, layout nem tokens de design: so configuracao de build, imports e tipos. "
                  "Se a correcao exigir mudar a UI, pare e reporte ao orquestrador (o agente frontend e o dono)."]
    return "\n".join(lines)


ROLES = []
for rid, (lang, act, cmds, focus, items) in REVIEWERS.items():
    ui = rid in ("react-reviewer", "vue-reviewer")
    ROLES.append(dict(
        id=rid, name="Revisor %s" % lang, kind="evaluator", group="stack-review", activation=act, level=3,
        responsibilities=["Revisar codigo %s: %s" % (lang, focus)],
        description="Revisor %s do AISEF: %s. Use quando a tarefa altera codigo %s%s." % (
            lang, focus, lang, " (ativacao manual; nao opina sobre layout nem design)" if ui else ""),
        source="ECC agents/%s.md" % ("typescript-reviewer" if rid == "typescript-reviewer" else rid),
        prompt_text=reviewer_prompt(lang, cmds, items) + (
            "\n\nVisual, layout, tipografia, cores e espacamento **nao** sao seus: sao da autoridade de design do projeto e do agente frontend."
            if ui else "")))
for rid, (lang, act, cmds, fixes) in RESOLVERS.items():
    ui = rid == "react-build-resolver"
    ROLES.append(dict(
        id=rid, name="Corretor de build %s" % lang.split(" (")[0], kind="fixer", group="stack-build", activation=act, level=3,
        responsibilities=["Fazer o build e a checagem de tipos %s passarem com diff minimo" % lang],
        description="Corretor de build %s do AISEF: faz build, checagem de tipos e lint voltarem a passar com diff minimo, sem refatorar nem afrouxar regras. Use quando o precheck ou o build falhar%s." % (
            lang, " (ativacao manual; nao mexe em UI)" if ui else ""),
        source="ECC agents/%s.md" % ("build-error-resolver" if rid in ("build-error-resolver", "python-build-resolver") else rid),
        prompt_text=resolver_prompt(lang, cmds, fixes, ui)))

# ------------------------------------------------------------------ dominio (manual) e acessibilidade (manual, so relata)
ROLES += [
    dict(id="rag-pipeline-reviewer", name="Revisor de pipeline RAG", kind="evaluator", group="domain-review", activation="domain:rag", level=3,
         responsibilities=["Revisar recuperacao, chunking, embeddings, avaliacao e seguranca de pipelines RAG"],
         description="Revisor RAG do AISEF: revisa recuperacao, chunking, embeddings, reranking, prompt de geracao, avaliacao e injecao de prompt em pipelines RAG. Ativado quando a deteccao acha RAG (bibliotecas de vetor ou de RAG).",
         source="ECC agents/rag-pipeline-reviewer.md",
         prompt_text="""
Voce revisa pipelines de recuperacao + geracao.

- **Recuperacao (HIGH)**: chunking sem sobreposicao ou cortando no meio de estruturas; tamanho do chunk incompativel com o modelo de embedding; metadados (fonte, data, permissao) ausentes; filtro de permissao aplicado depois da busca (vaza documento).
- **Embeddings (HIGH)**: modelo de consulta diferente do de indexacao; reindexacao esquecida quando o modelo muda; normalizacao inconsistente.
- **Geracao (HIGH)**: contexto sem citacao da fonte; resposta sem "nao sei" quando a recuperacao vem vazia; limite de contexto estourado sem corte controlado.
- **Seguranca (CRITICAL)**: documento recuperado tratado como instrucao (injecao indireta de prompt); dado sensivel indexado sem controle de acesso.
- **Avaliacao (HIGH)**: sem conjunto de avaliacao (precisao da recuperacao, fidelidade, relevancia) nem regressao quando muda chunking, modelo ou prompt.
"""),
    dict(id="mle-reviewer", name="Revisor de engenharia de ML", kind="evaluator", group="domain-review", activation="domain:ml", level=3,
         responsibilities=["Revisar contratos de dados, pipelines de features, reprodutibilidade, avaliacao e entrega de modelos"],
         description="Revisor de ML do AISEF: revisa contratos de dados, pipelines de features, reprodutibilidade do treino, avaliacao offline, servico, monitoramento e rollback de modelos. Ativado quando a deteccao acha ML (PyTorch, scikit-learn, TensorFlow...).",
         source="ECC agents/mle-reviewer.md",
         prompt_text="""
Voce revisa ML de producao.

- **Dados (HIGH)**: contrato de schema ausente; vazamento entre treino e teste (dado do futuro, duplicata, alvo nas features); divisao nao estratificada quando deveria.
- **Reprodutibilidade (HIGH)**: semente, versao dos dados, do codigo e das dependencias nao registradas; artefato sem linhagem.
- **Features (HIGH)**: transformacao diferente no treino e no servico (skew); estatistica calculada no conjunto inteiro antes de dividir.
- **Avaliacao (HIGH)**: metrica que nao reflete o objetivo de negocio; sem baseline; sem analise por fatia; limiar escolhido no teste.
- **Servico (HIGH)**: sem validacao de entrada; sem versao do modelo na resposta e no log; sem plano de rollback nem shadow/canary; sem monitoramento de deriva.
"""),
    dict(id="healthcare-reviewer", name="Revisor de software de saude", kind="evaluator", group="domain-review", activation="manual", level=5,
         responsibilities=["Revisar seguranca clinica, apoio a decisao clinica, protecao de dados de saude e integridade de dados medicos"],
         description="Revisor de saude do AISEF: revisa seguranca clinica, apoio a decisao clinica, protecao de dados de saude (LGPD, HIPAA) e integridade de dados medicos. Ativacao manual, para projetos de saude.",
         source="ECC agents/healthcare-reviewer.md",
         prompt_text="""
Voce revisa software de saude com foco em seguranca do paciente.

- **Seguranca clinica (CRITICAL)**: calculo de dose, unidade ou conversao sem teste e sem validacao de faixa; alerta clinico que pode ser suprimido sem registro; arredondamento que muda decisao clinica.
- **Apoio a decisao (CRITICAL)**: regra clinica sem fonte citada (diretriz, versao); recomendacao apresentada como diagnostico; ausencia de revisao humana onde a norma exige.
- **Dados de saude (CRITICAL)**: dado sensivel em log, URL, analytics ou ambiente de teste; acesso sem trilha de auditoria; minimo necessario nao respeitado (LGPD art. 11, HIPAA).
- **Integridade (HIGH)**: identificacao do paciente ambigua; registro clinico alteravel sem historico; fuso e data de evento clinico inconsistentes; interoperabilidade (HL7, FHIR) sem validacao de perfil.
Nao de parecer medico: aponte o risco e a norma; a decisao clinica e de profissional habilitado.
"""),
    dict(id="a11y-architect", name="Revisor de acessibilidade", kind="evaluator", group="stack-review", activation="manual", level=3,
         responsibilities=["Revisar conformidade com WCAG 2.2 em web e apps nativos, sem alterar design"],
         description="Revisor de acessibilidade do AISEF: revisa conformidade WCAG 2.2 (teclado, leitor de tela, contraste, foco, rotulos, movimento) em web e apps nativos e relata achados, sem alterar o design. Ativacao manual.",
         source="ECC agents/a11y-architect.md",
         prompt_text="""
Voce **relata**; nao edita. Achado que exige mudanca visual (cor, contraste, tamanho) vira proposta para a autoridade de design do projeto e para o agente frontend, nunca alteracao direta.

## Checklist WCAG 2.2 (A e AA)
- **Teclado**: todo controle alcancavel e operavel por teclado; ordem de foco logica; foco visivel e nao encoberto (2.4.11); sem armadilha de foco; atalhos desligaveis.
- **Leitor de tela**: nome, papel e valor acessiveis; rotulo em todo campo; erro de formulario anunciado e associado ao campo; regioes e titulos estruturados; imagem com texto alternativo adequado.
- **Visual**: contraste 4,5:1 (texto) e 3:1 (componentes e graficos); informacao nao so por cor; alvo de toque de pelo menos 24x24 px (2.5.8); conteudo legivel com zoom de 200% e em 320 px.
- **Movimento e tempo**: respeitar `prefers-reduced-motion`; nada piscando mais de 3 vezes por segundo; tempo limite ajustavel.
- **Entrada**: alternativa a arrastar (2.5.7); autenticacao sem teste cognitivo (3.3.8); nao pedir de novo o que ja foi informado (3.3.7).
Evidencia: ferramenta usada (axe, Lighthouse, leitor de tela), tela, criterio WCAG e passo para reproduzir.
"""),
]
