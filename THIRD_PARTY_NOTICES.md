# Avisos de terceiros

## everything-claude-code (ECC)

Partes do AISEF adaptam textos e ideias do projeto [everything-claude-code](https://github.com/affaan-m/everything-claude-code). Nenhum código ou hook do ECC é instalado ou executado; o texto foi reescrito em pt-BR para o Agent Contract e o Execution Gateway do AISEF. Arquivos derivados:
- prompts dos agentes em `plugins/aisef/core/agents/prompts/` (o campo `source` do catálogo `core/agents/catalog.v0.1.json` diz de qual agente do ECC cada um veio);
- práticas em `plugins/aisef/core/practices/` (derivadas de `rules/` e de skills do ECC, quando indicado no cabeçalho);
- mapeamento de stacks em `plugins/aisef/core/detect/stacks.v0.1.json` (derivado de `config/project-stack-mappings.json` e `scripts/lib/project-detect.js`).

Licença do ECC:

```
MIT License

Copyright (c) 2026 Affaan Mustafa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
