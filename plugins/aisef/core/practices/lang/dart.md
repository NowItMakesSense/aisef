---
paths:
  - "**/*.dart"
description: Praticas de Dart e Flutter
source: ECC rules/dart (MIT), condensado
---

# Dart e Flutter

- `dart analyze` limpo com as regras do projeto; null safety sem `!` desnecessário.
- Widgets pequenos e `const` quando possível; lógica fora do widget, no padrão de estado escolhido (Bloc, Riverpod, Provider).
- `dispose` de controllers e streams; checar `mounted` antes de usar `context` após `await`.
- Listas longas com `ListView.builder`; imagens com cache e tamanho adequado.
- Credenciais em armazenamento seguro; testes de widget e de unidade com `flutter test`.
