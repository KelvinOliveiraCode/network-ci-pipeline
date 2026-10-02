"""Testes do estagio de golden config.

Golden config stage tests.

Este e o estagio com a regra de ouro mais importante do projeto: **golden config
nao e igualdade estrita**. Se fosse, toda mudanca legitima seria reprovada e
o time aprenderia a ignorar o pipeline - que e o oposto do que um pipeline
serve.

Metade destes testes existe para provar exatamente isso: os tres candidatos
aprovados passam, e eles sao diferentes entre si de proposito. `switch-ok-2`
tem uma VLAN e uma interface a mais; `switch-ok-3` tem uma interface a menos.
Nenhum dos dois pode ser reprovado.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from netci import golden
from netci.achado import ERRO
from netci.parser import parse_arquivo, parse_texto

RAIZ = Path(__file__).resolve().parent.parent
GOLDEN = RAIZ / "dados" / "golden" / "switch-core.cfg"


def _codigos(achados) -> set[str]:
    return {a.codigo for a in achados}


@pytest.fixture
def referencia():
    return parse_arquivo(GOLDEN)


class TestOsAprovadosPassam:
    """Os tres candidatos que tem de passar."""

    @pytest.mark.parametrize(
        "nome",
        ["switch-ok-1", "switch-ok-2", "switch-ok-3"],
    )
    def test_candidato_aprovado(self, nome: str, referencia) -> None:
        config = parse_arquivo(RAIZ / "dados" / "candidatos" / f"{nome}.cfg")
        achados = golden.comparar(config, referencia)
        bloqueantes = [a for a in achados if a.severidade == ERRO]
        assert not bloqueantes, [a.resumo() for a in bloqueantes]

    def test_vlan_a_mais_avisa_mas_nao_bloqueia(self, referencia) -> None:
        config = parse_arquivo(RAIZ / "dados" / "candidatos" / "switch-ok-2.cfg")
        achados = golden.comparar(config, referencia)
        novos = [a for a in achados if a.codigo == "VLAN_NOVA"]
        assert novos, "a VLAN 50 deveria ser avisada"
        assert all(a.severidade != ERRO for a in novos)
        assert "50" in novos[0].mensagem

    def test_interface_a_menos_nao_e_achado(self, referencia) -> None:
        # `switch-ok-3` nao tem a Gi0/4, que existe no golden. Faltou
        # configuracao opcional, e o estagio nao e dono dessa decisao.
        config = parse_arquivo(RAIZ / "dados" / "candidatos" / "switch-ok-3.cfg")
        achados = golden.comparar(config, referencia)
        assert not any("Gi0/4" in a.mensagem for a in achados)


class TestAusenciasEstruturais:
    """O que nao pode faltar em config saudavel."""

    def _sem(self, referencia, texto: str):
        return golden.comparar(parse_texto(texto), referencia)

    def test_sem_enable_secret(self, referencia) -> None:
        achados = self._sem(referencia, "hostname X\nvlan 10\n")
        assert "SEM_ENABLE_SECRET" in _codigos(achados)

    def test_sem_line_vty(self, referencia) -> None:
        texto = "hostname X\nvlan 10\nenable secret Y\n"
        assert "SEM_LINE_VTY" in _codigos(self._sem(referencia, texto))

    def test_vty_sem_password(self, referencia) -> None:
        texto = (
            "hostname X\nvlan 10\nenable secret Y\n"
            "line vty 0 4\n transport input ssh\n"
        )
        assert "VTY_SEM_PASSWORD" in _codigos(self._sem(referencia, texto))

    def test_sem_deney_final(self, referencia) -> None:
        texto = (
            "hostname X\nvlan 10\nenable secret Y\n"
            "line vty 0 4\n password P\n"
            "access-list 100 permit tcp any any eq 22\n"
        )
        assert "ACL_SEM_DENY_ANY" in _codigos(self._sem(referencia, texto))

    def test_sem_spanning_tree(self, referencia) -> None:
        texto = (
            "hostname X\nvlan 10\nenable secret Y\n"
            "line vty 0 4\n password P\n"
            "access-list 100 deny ip any any\n"
            "interface Gi0/1\n switchport mode trunk\n"
        )
        assert "SEM_SPANNING_TREE" in _codigos(self._sem(referencia, texto))

    def test_sem_trunk(self, referencia) -> None:
        texto = (
            "hostname X\nvlan 10\nenable secret Y\n"
            "line vty 0 4\n password P\n"
            "access-list 100 deny ip any any\n"
            "spanning-tree mode rapid-pvst\n"
            "interface Gi0/1\n switchport mode access\n"
        )
        assert "SEM_INTERFACE_TRUNK" in _codigos(self._sem(referencia, texto))

    def test_config_vazia_e_cheia_de_erros(self, referencia) -> None:
        codigos = _codigos(self._sem(referencia, "hostname X\n"))
        assert "SEM_ENABLE_SECRET" in codigos
        assert "SEM_LINE_VTY" in codigos
        assert "SEM_SPANNING_TREE" in codigos


class TestGoldenContraSiMesmo:
    """O golden tem de passar contra ele mesmo."""

    def test_golden_nao_acusa_a_si_mesmo(self, referencia) -> None:
        achados = golden.comparar(referencia, referencia)
        bloqueantes = [a for a in achados if a.severidade == ERRO]
        assert not bloqueantes, [a.resumo() for a in bloqueantes]

    def test_golden_nao_avisa_sobre_si_mesmo(self, referencia) -> None:
        achados = golden.comparar(referencia, referencia)
        assert not any(a.codigo == "VLAN_NOVA" for a in achados)


class TestOrm:
    """O contrato com o resto do pipeline."""

    def test_tabela_declara_cada_regra(self) -> None:
        codigos = {r.codigo for r in golden.tabela()}
        assert len(codigos) >= 7

    def test_achados_tem_estagio_golden(self, referencia) -> None:
        for a in golden.comparar(parse_texto("hostname X\n"), referencia):
            assert a.estagio == "golden"

    def test_codigos_sao_unicos(self) -> None:
        codigos = [r.codigo for r in golden.tabela()]
        assert len(codigos) == len(set(codigos))