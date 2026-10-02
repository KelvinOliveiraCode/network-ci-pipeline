"""Testes do estagio de regras de negocio.

Business rules stage tests.

A diferenca entre um estagio que pega problema e um que enche o relatorio de
laje e quantos achados ele faz **em um arquivo que esta certo**. Por isso,
metade destes testes usa `switch-ok-1.cfg`, que tem de sair limpo: uma regra
que acusa o arquivo bom nao esta protegendo, esta atrapalhando.

E a outra metade usa config montada na mao, para que cada regra seja testada
so, sem as outras mascarando o resultado.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from netci import regras
from netci.achado import ERRO
from netci.parser import parse_arquivo, parse_texto

RAIZ = Path(__file__).resolve().parent.parent
OK = RAIZ / "dados" / "candidatos" / "switch-ok-1.cfg"


def _codigos(achados) -> set[str]:
    return {a.codigo for a in achados}


class TestArquivoBom:
    """O arquivo que tem de passar limpo."""

    def test_ok_1_nao_acusa(self) -> None:
        achados = [a for a in regras.validar(parse_arquivo(OK)) if a.bloqueia]
        assert not achados, [a.resumo() for a in achados]


class TestVlanDuplicada:
    """A mesma VLAN declarada duas vezes."""

    def test_acusa_a_segunda_declaracao(self) -> None:
        config = parse_texto("vlan 10\n name A\nvlan 20\nvlan 10\n name B\n")
        achados = regras.validar(config)
        duplicadas = [a for a in achados if a.codigo == "VLAN_DUPLICADA"]
        assert len(duplicadas) == 1
        # A linha apontada e a da segunda, que e a que alguem vai corrigir.
        assert duplicadas[0].linha == 4

    def test_a_sugestao_aponta_a_primeira(self) -> None:
        config = parse_texto("vlan 10\nvlan 10\n")
        achado = next(a for a in regras.validar(config) if a.codigo == "VLAN_DUPLICADA")
        assert "1" in achado.sugestao

    def test_vlan_uma_vez_nao_acusa(self) -> None:
        config = parse_texto("vlan 10\nvlan 20\nvlan 30\n")
        assert "VLAN_DUPLICADA" not in _codigos(regras.validar(config))


class TestAclSemDeny:
    """A ACL sem o `deny` final, que deixa passar tudo."""

    def test_acusa_acl_sem_deny(self) -> None:
        config = parse_texto(
            "access-list 100 permit tcp any any eq 22\n"
            "access-list 100 permit tcp any any eq 443\n"
        )
        assert "ACL_SEM_DENY" in _codigos(regras.validar(config))

    def test_nao_acusa_quando_o_deny_existe(self) -> None:
        config = parse_texto(
            "access-list 100 permit tcp any any eq 22\n"
            "access-list 100 deny ip any any\n"
        )
        assert "ACL_SEM_DENY" not in _codigos(regras.validar(config))

    def test_um_deny_no_meio_nao_conta(self) -> None:
        # O `deny` precisa ser o ULTIMO. Um deny no meio e um erro de
        # logica que permite o trafego seguinte, que e o que a regra procura.
        config = parse_texto(
            "access-list 100 deny ip any any\n"
            "access-list 100 permit tcp any any eq 22\n"
        )
        assert "ACL_SEM_DENY" in _codigos(regras.validar(config))


class TestRotaPadrao:
    """Rota padrao declarada mais de uma vez."""

    def test_acusa_duplicada(self) -> None:
        config = parse_texto(
            "ip route 0.0.0.0 255.255.255.0 192.168.20.1\n"
            "ip route 0.0.0.0 255.255.255.0 192.168.10.1\n"
        )
        assert "ROTA_PADRAO_DUPLICADA" in _codigos(regras.validar(config))

    def test_nao_acusa_uma_rota_padrao(self) -> None:
        config = parse_texto("ip route 0.0.0.0 255.255.255.0 192.168.20.1\n")
        assert "ROTA_PADRAO_DUPLICADA" not in _codigos(regras.validar(config))

    def test_nao_acusa_rota_nao_padrao_repetida(self) -> None:
        config = parse_texto(
            "ip route 10.1.0.0 255.255.0.0 192.168.20.1\n"
            "ip route 10.2.0.0 255.255.0.0 192.168.20.2\n"
        )
        assert "ROTA_PADRAO_DUPLICADA" not in _codigos(regras.validar(config))


class TestRotaParaSi:
    """Rota cujo proximo salto e a propria interface."""

    def test_acusa_rota_para_si(self) -> None:
        config = parse_texto(
            "interface Vlan30\n"
            " ip address 192.168.30.2 255.255.255.0\n"
            "ip route 0.0.0.0 255.255.255.0 192.168.30.2\n"
        )
        assert "ROTA_PARA_SI" in _codigos(regras.validar(config))

    def test_nao_acusa_rota_para_outra_interface(self) -> None:
        config = parse_texto(
            "interface Vlan30\n"
            " ip address 192.168.30.2 255.255.255.0\n"
            "ip route 0.0.0.0 255.255.255.0 192.168.20.1\n"
        )
        assert "ROTA_PARA_SI" not in _codigos(regras.validar(config))


class TestSemMascara:
    """`ip address` sem mascara."""

    def test_acusa(self) -> None:
        config = parse_texto(
            "interface Vlan30\n"
            " ip address 192.168.30.2\n"
        )
        assert "SEM_MASCARA" in _codigos(regras.validar(config))

    def test_nao_acusa_com_mascara(self) -> None:
        config = parse_texto(
            "interface Vlan30\n"
            " ip address 192.168.30.2 255.255.255.0\n"
        )
        assert "SEM_MASCARA" not in _codigos(regras.validar(config))


class TestAvisos:
    """As regras que avisam mas nao bloqueiam."""

    def test_sem_filtro_de_entrada_avisa(self) -> None:
        config = parse_texto("hostname X\nvlan 10\n")
        achado = next(
            a for a in regras.validar(config) if a.codigo == "SEM_FILTRO_DE_ENTRADA"
        )
        assert achado.severidade != ERRO

    def test_vlan_sem_interface_avisa(self) -> None:
        config = parse_texto(
            "vlan 10\n"
            "vlan 20\n"
            "interface Gi0/1\n"
            " switchport access vlan 10\n"
        )
        achado = next(
            a for a in regras.validar(config) if a.codigo == "VLAN_SEM_INTERFACE"
        )
        # A mensagem tem que dizer qual VLAN, senao o revisor precisa
        # contar as declaracoes para achar a orfa.
        assert "20" in achado.mensagem


class TestOrm:
    """O contrato com o resto do pipeline."""

    def test_tabela_tem_todas_as_regras(self) -> None:
        codigos = {r.codigo for r in regras.tabela()}
        for esperado in (
            "VLAN_DUPLICADA",
            "ACL_SEM_DENY",
            "ROTA_PADRAO_DUPLICADA",
            "ROTA_PARA_SI",
            "SEM_MASCARA",
            "SEM_FILTRO_DE_ENTRADA",
            "VLAN_SEM_INTERFACE",
        ):
            assert esperado in codigos, f"falta {esperado} na tabela"

    def test_achados_ordenados_por_linha(self) -> None:
        config = parse_texto(
            "vlan 10\nvlan 10\naccess-list 100 permit ip any any\n"
        )
        achados = regras.validar(config)
        linhas = [a.linha for a in achados if a.linha]
        assert linhas == sorted(linhas)

    def test_nenhum_achado_sem_estagio(self) -> None:
        config = parse_texto("vlan 10\nvlan 10\n")
        for a in regras.validar(config):
            assert a.estagio == "regras"

    def test_arquivo_com_regra_ruim_e_reprovado_na_stage_certa(self) -> None:
        ruins = RAIZ / "dados" / "candidatos" / "switch-ruins-regras.cfg"
        achados = regras.validar(parse_arquivo(ruins))
        bloqueantes = [a for a in achados if a.bloqueia]
        assert bloqueantes
        assert "VLAN_DUPLICADA" in _codigos(achados)
        assert "ACL_SEM_DENY" in _codigos(achados)