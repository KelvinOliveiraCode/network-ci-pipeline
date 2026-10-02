"""Confere que nenhum arquivo do projeto saiu corrompido.

Check that no file in the project came out corrupted.

Neste host ja surgiram ideogramas CJK em arquivo que deveria ter acentos
portugueses: um caractere trocado por outro de outra codificacao, e o
conteudo muda sem ninguem perceber. Nao e erro de logica - e corrupcao de
encoding, que passa despercebida numa revisao com pressa. Falhar aqui e mais
barato do que achar isso num README publicado.

Tres criterios:

1. **Sem U+FFFD**, o caractere de substituicao. Onde ele aparece, algo foi
   decodificado errado antes. E sempre erro.
2. **Sem CJK.** Um arquivo em portugues ou ingles nao tem motivo para ter
   ideograma, kana ou hangul, e a presenca significa que a leitura usou a
   codificacao errada em algum ponto.
3. **Codigo e dados sao ASCII.** Comentario e Markdown podem ter acento;
   arquivo executavel e dado de configuracao nao.

O terceiro criterio e o que pega o resto. Um acento perdido em um YAML nao
quebra o parse, e um CJK dentro de uma string de configuracao vira um comando
que o equipamento nao entende.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Diretorios que nao sao fonte do projeto.
IGNORAR_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "node_modules",
}

# Arquivos que existem na pasta mas nao tem texto para conferir. `.coverage`
# e binario, e include-lo trava a leitura do script inteiro.
IGNORAR_ARQUIVOS = {
    ".coverage",
    "coverage.xml",
    "Thumbs.db",
    "Desktop.ini",
}

# Temporarios meus e dos subagents.
PREFIXOS_TEMPORARIOS = ("out-", "tmp_", "out.")

# Extensoes de texto. `.cfg` e a configuracao, que tem de ser ASCII.
EXTENSOES = {
    ".py", ".yaml", ".yml", ".md", ".txt", ".cfg", ".toml", ".json",
}

# Extensoes que tem de ser ASCII puro.
ASCII_PURO = {".py", ".yaml", ".yml", ".cfg", ".toml"}

# Faixas CJK: unificados, kana, hangul, compatibilidade e meia largura.
FAIXAS_CJK = (
    (0x2E80, 0x2EFF),
    (0x3000, 0x303F),
    (0x3040, 0x30FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xA000, 0xA4CF),
    (0xAC00, 0xD7AF),
    (0xF900, 0xFAFF),
    (0xFF00, 0xFFEF),
)


def _tem_cjk(caractere: str) -> bool:
    """Se o caractere esta em alguma faixa CJK.

    Whether the character is in a CJK range.

    Args:
        caractere: Um caractere.

    Returns:
        Verdadeiro se for ideograma, kana ou hangul.
    """
    ponto = ord(caractere)
    return any(inicio <= ponto <= fim for inicio, fim in FAIXAS_CJK)


def arquivos() -> list[Path]:
    """Os arquivos de texto do projeto.

    The project's text files.

    Returns:
        Todos os arquivos com extensao conhecida, exceto os ignorados.
    """
    encontrados: list[Path] = []
    for caminho in RAIZ.rglob("*"):
        if not caminho.is_file():
            continue
        if any(parte in IGNORAR_DIRS for parte in caminho.parts):
            continue
        if caminho.name in IGNORAR_ARQUIVOS:
            continue
        if caminho.name.startswith(PREFIXOS_TEMPORARIOS):
            continue
        if caminho.suffix.lower() in EXTENSOES or caminho.name.startswith("."):
            encontrados.append(caminho)
    return sorted(encontrados)


def _rotulo(caminho: Path) -> Path:
    """O caminho como o relatorio mostra: relativo se estiver no repositorio.

    The path as the report shows it: relative when inside the repository.

    Args:
        caminho: O arquivo.

    Returns:
        O caminho relativo ao repositorio, ou o caminho absoluto.
    """
    try:
        return caminho.relative_to(RAIZ)
    except ValueError:
        return caminho


def confere(caminho: Path) -> list[str]:
    """Confere um arquivo.

    Check one file.

    Args:
        caminho: O arquivo.

    Returns:
        Uma mensagem por problema. Vazio significa ok.
    """
    try:
        texto = caminho.read_text(encoding="utf-8")
    except UnicodeDecodeError as erro:
        return [f"{_rotulo(caminho)}: nao decodifica como UTF-8 ({erro.reason})"]

    problemas: list[str] = []
    # `relative_to` levanta para arquivo fora do repositorio, e o portao
    # precisa funcionar em qualquer caminho: e assim que os testes o exercitam
    # com arquivo plantado em diretorio temporario. Sem este `try`, o portao
    # quebra justamente nos testes que provam que ele funciona.
    try:
        relativo = caminho.relative_to(RAIZ)
    except ValueError:
        relativo = caminho
    ascii_puro = caminho.suffix.lower() in ASCII_PURO

    for numero, linha in enumerate(texto.splitlines(), start=1):
        if "\ufffd" in linha:
            problemas.append(f"{relativo}:{numero}: U+FFFD (caractere de substituicao)")

        for caractere in linha:
            ponto = ord(caractere)
            if _tem_cjk(caractere):
                problemas.append(
                    f"{relativo}:{numero}: caractere CJK {caractere!r} U+{ponto:04X}"
                )
                break
            if ascii_puro and ponto > 127:
                problemas.append(
                    f"{relativo}:{numero}: caractere nao-ASCII {caractere!r} "
                    f"U+{ponto:04X} em codigo"
                )
                break

    return problemas


def principal() -> int:
    """Roda a conferencia em todos os arquivos.

    Run the check over all files.

    Returns:
        0 se nenhum problema, 1 se algum.
    """
    problemas: list[str] = []
    lista = arquivos()
    for caminho in lista:
        problemas.extend(confere(caminho))

    if problemas:
        print("encoding FALHOU:")
        for problema in problemas:
            # A mensagem de problema carrega o caractere culpado, e o
            # culpado e justamente um caractere que o console pode nao
            # saber imprimir. Sem o escape, o portao quebra ao relatar o
            # problema que ele existe para relatar - e um portao que quebra
            # nao diz nada, o que e pior do que um portao que passa.
            print("  ", _seguro(problema))
        return 1

    print(
        f"encoding ok: {len(lista)} arquivo(s), nenhum U+FFFD, nenhum CJK, "
        "nenhum caractere nao-ASCII em codigo ou dado"
    )
    return 0


def _seguro(texto: str) -> str:
    """O texto, com o que o console nao sabe imprimir escapado.

    The text, with whatever the console cannot print escaped.

    O console do Windows e cp1252 por padrao. Um ideograma nao existe la, e
    `print` levanta UnicodeEncodeError em vez de imprimir. Como este e um
    projeto Windows-first e a regra existe justamente para pegar esses
    caracteres, o portao precisa sobreviver a eles.

    Args:
        texto: A mensagem original.

    Returns:
        A mensagem com caracteres nao imprimiveis virados em `\\uXXXX`.
    """
    try:
        texto.encode(sys.stdout.encoding or "utf-8")
        return texto
    except (UnicodeEncodeError, LookupError):
        return texto.encode("ascii", "backslashreplace").decode("ascii")


if __name__ == "__main__":
    raise SystemExit(principal())