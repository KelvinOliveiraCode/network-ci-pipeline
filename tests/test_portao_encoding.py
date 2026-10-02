"""Testes do portao de encoding.

Encoding gate tests.

Um portao que quebra ao relatar o problema que ele existe para relatar e
pior do que um portao que passa: o primeiro nao diz nada, e quem confia nele
descobre o problema em producao.

O console do Windows e cp1252 por padrao, e um ideograma nao existe la. Por
isso estes testes existem: plantam o problema de verdade e conferem que o
portao sobrevive e ainda assim reprova.

O criterio tambem cobre o terceiro ponto - codigo ASCII puro - que e o que
pega um acento perdido em um dado de configuracao, onde o parse passa e o
comando fica errado.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def _carrega_portao():
    """Importa `tools/verificar_encoding.py` como modulo.

    Load the gate script as a module.

    Returns:
        O modulo carregado.
    """
    caminho = RAIZ / "tools" / "verificar_encoding.py"
    spec = importlib.util.spec_from_file_location("portao_encoding", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def portao():
    return _carrega_portao()


class TestDetectaProblemas:
    """O portao tem de achar o que foi plantado."""

    def test_ideograma_cjk(self, portao, tmp_path: Path) -> None:
        arquivo = tmp_path / "x.cfg"
        arquivo.write_text("hostname X\n! ideograma: \u771f\n", encoding="utf-8")
        problemas = portao.confere(arquivo)
        assert any("CJK" in p for p in problemas), problemas

    def test_u_fffd(self, portao, tmp_path: Path) -> None:
        arquivo = tmp_path / "x.md"
        arquivo.write_text("texto com \ufffd aqui\n", encoding="utf-8")
        problemas = portao.confere(arquivo)
        assert any("U+FFFD" in p for p in problemas)

    def test_acento_em_codigo_falha(self, portao, tmp_path: Path) -> None:
        # Este e o criterio mais importante: um acento em .py ou .cfg nao
        # quebra o parse, entao passa despercebido e vira conteudo errado.
        arquivo = tmp_path / "x.cfg"
        arquivo.write_text("description estacao \u00e7\n", encoding="utf-8")
        problemas = portao.confere(arquivo)
        assert any("nao-ASCII" in p for p in problemas)

    def test_acento_em_markdown_passa(self, portao, tmp_path: Path) -> None:
        # Markdown pode ter acento: e um documento, nao codigo.
        arquivo = tmp_path / "x.md"
        arquivo.write_text("# Configura\u00e7\u00e3o de rede\n", encoding="utf-8")
        assert portao.confere(arquivo) == []

    def test_arquivo_ascii_puro_passa(self, portao, tmp_path: Path) -> None:
        arquivo = tmp_path / "x.cfg"
        arquivo.write_text("hostname SW-1\nvlan 10\n", encoding="utf-8")
        assert portao.confere(arquivo) == []

    def test_arquivo_que_nao_decodifica(self, portao, tmp_path: Path) -> None:
        arquivo = tmp_path / "x.cfg"
        arquivo.write_bytes(b"hostname \xff\xfe\n")
        problemas = portao.confere(arquivo)
        assert any("UTF-8" in p for p in problemas)


class TestSobreviveAoQueDetecta:
    """O portao nao pode quebrar ao relatar."""

    def test_ideograma_e_escapado_na_mensagem(self, portao, tmp_path: Path) -> None:
        # O culpado e justamente um caractere que o console pode nao saber
        # imprimir. Se `print` levantar aqui, o portao morre no primeiro
        # achado e devolve traceback em vez de exit 1.
        arquivo = tmp_path / "x.cfg"
        arquivo.write_text("! ideograma: \u771f\n", encoding="utf-8")
        problemas = portao.confere(arquivo)
        assert problemas, "o problema deveria ter sido achado"
        # Todo problema tem de ser imprimivel.
        for problema in problemas:
            escapado = portao._seguro(problema)
            escapado.encode(sys.stdout.encoding or "utf-8")

    def test_seguro_devolve_o_texto_quando_da(self, portao) -> None:
        assert portao._seguro("texto normal") == "texto normal"

    def test_seguro_escapa_quando_nao_da(self, portao, monkeypatch) -> None:
        # O caminho que importa e o do console do Windows, que e cp1252 e
        # nao tem ideograma. Sob pytest o stdout e utf-8 e nao haveria o que
        # escapar, entao o encoding e forjado para exercitar o caminho real.
        monkeypatch.setattr(sys, "stdout", _SaidaFalsa("cp1252"))
        escapado = portao._seguro("ideograma \u771f aqui")
        assert "\ufffd" not in escapado
        escapado.encode("cp1252")  # agora e imprimivel no console do host

    def test_seguro_e_garantido_para_o_encoding_real(self, portao) -> None:
        for problema in ("ideograma \u771f", "acento \u00e7", "normal"):
            portao._seguro(problema).encode(
                sys.stdout.encoding or "utf-8", errors="strict"
            )


class _SaidaFalsa:
    """Um stdout que finge ter um encoding diferente.

    A stdout that pretends to have a different encoding.

    O portao le `sys.stdout.encoding` para decidir o que escapar. Sem esta
    classe o teste nunca exercitaria o caminho de escape, porque sob pytest o
    encoding ja e utf-8 e nada precisa ser escapado.

    Attributes:
        encoding: O encoding que este objeto finge ter.
    """

    def __init__(self, encoding: str) -> None:
        self.encoding = encoding

    def write(self, texto: str) -> int:
        """Aceita qualquer texto, sem codificar.

        Accept any text, without encoding.

        Args:
            texto: O texto.

        Returns:
            Zero.
        """
        return 0

    def flush(self) -> None:
        """Nao faz nada.

        Does nothing.
        """


class TestNaoVarreOQueNaoDEve:
    """O portao ignora o que nao e texto."""

    def test_ignora_coverage_binario(self, portao) -> None:
        # `.coverage` e binario. Inclui-lo trava a leitura do script inteiro.
        assert ".coverage" in portao.IGNORAR_ARQUIVOS

    def test_ignora_temporarios(self, portao) -> None:
        assert any(p.startswith("tmp_") for p in portao.PREFIXOS_TEMPORARIOS)
        assert any(p.startswith("out-") for p in portao.PREFIXOS_TEMPORARIOS)

    def test_ignora_pycache(self, portao) -> None:
        assert "__pycache__" in portao.IGNORAR_DIRS

    def test_arquivos_nao_inclui_pycache(self, portao) -> None:
        for caminho in portao.arquivos():
            assert "__pycache__" not in caminho.parts


class TestOProjetoPassa:
    """O portao tem de passar no estado real do repositorio."""

    def test_o_projeto_atual_passa(self, portao) -> None:
        problemas: list[str] = []
        for caminho in portao.arquivos():
            problemas.extend(portao.confere(caminho))
        assert not problemas, problemas

    def test_tem_arquivo_para_conferir(self, portao) -> None:
        assert len(portao.arquivos()) > 10