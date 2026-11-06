"""Bibliotecas instaladas na pasta de usuario do pip (jsonschema, cryptography).

Sem permissao de escrita no Python do sistema (comum no Windows), `pip install` grava em
%APPDATA%/Python/PythonXY/site-packages, e o `python -I` dos hooks e scripts ignora essa pasta.
Importar este modulo a acrescenta ao FIM do sys.path: a biblioteca padrao e o plugin continuam com
precedencia, e plantar um modulo ali exige escrever na conta do usuario. Somente stdlib.
"""
import site
import sys

USER_SITE = site.getusersitepackages()
if USER_SITE not in sys.path:
    sys.path.append(USER_SITE)
