"""Testes do estagio de teste de conectividade.

Simulated connectivity stage tests.

O estagio tem tres saidas possiveis - caminho existe, caminho nao existe,
caminho bloqueado - e os tres precisam estar testados com o mesmo cuidado. Um
teste de conectividade que so verifica o caminho feliz passa em codigo que
aprova rota inexistente, que e o tipo de bug que so aparece quando o servico
ja esta fora do ar.

Nenhum teste abre socket: o modulo inteiro e logica de enderecamento.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from netci import testes
from netci.parser import parse_arquivo, parse_texto

RAIZ = Path(__file__).resolve().parent.parent
GOLDEN = RAIZ / "dados" / "golden" / "switch-core.cfg"

COM_ROTA = (
    "interface Vlan30\n"
    " ip address 192.168.30.2 255.255.255.0\n"
    "ip route 192.168.20.0 255.255.255.0 192.168.30.1\n"
)

COM_ACL_NEGA = COM_ROTA + "access-list 100 deny ip any any\n"


def _um(config, origem: str, destino: str):
    """Roda o teste e devolve o achado unico.

    Run the test and return the single finding.

    Args:
        config: A configuracao.
        origem: Endereco de origem.
        destino: Endereco de destino.

    Returns:
        O achado.
    """
    achados = testes.testar(config, origem, destino)
    assert len(achados) == 1, "o estagio devolve exatamente um achado"
    return achados[0]


class TestCaminhoQueExiste:
    """O caminho existe."""

    def test_mesma_subnet_permite(self) -> None:
        config = parse_texto(COM_ROTA)
        achado = _um(config, "192.168.30.2", "192.168.30.99")
        assert achado.codigo == "TESTE_OK"
        assert achado.severidade != "erro", "caminho que existe nao bloqueia"

    def test_rota_permite(self) -> None:
        config = parse_texto(COM_ROTA)
        achado = _um(config, "192.168.30.2", "192.168.20.10")
        assert achado.codigo == "TESTE_OK"

    def test_rota_padrao_alcanca_tudo(self) -> None:
        config = parse_texto(
            "interface Vlan30\n"
            " ip address 192.168.30.2 255.255.255.0\n"
            "ip route 0.0.0.0 0.0.0.0 192.168.30.1\n"
        )
        assert _um(config, "192.168.30.2", "10.1.2.3").codigo == "TESTE_OK"

    def test_a_mensagem_diz_por_qual_caminho(self) -> None:
        config = parse_texto(COM_ROTA)
        achado = _um(config, "192.168.30.2", "192.168.20.10")
        assert "rota" in achado.mensagem


class TestCaminhoQueNaoExiste:
    """Nao ha caminho."""

    def test_sem_subnet_e_sem_rota(self) -> None:
        config = parse_texto(
            "interface Vlan30\n"
            " ip address 192.168.30.2 255.255.255.0\n"
        )
        achado = _um(config, "192.168.30.2", "10.9.9.9")
        assert achado.codigo == "TESTE_SEM_CAMINHO"
        assert achado.severidade == "erro"

    def test_a_mensagem_cita_os_dois_enderecos(self) -> None:
        config = parse_texto(
            "interface Vlan30\n"
            " ip address 192.168.30.2 255.255.255.0\n"
        )
        achado = _um(config, "192.168.30.2", "10.9.9.9")
        assert "192.168.30.2" in achado.mensagem
        assert "10.9.9.9" in achado.mensagem


class TestAclBloqueia:
    """O caminho existe mas a ACL fecha."""

    def test_deny_implicito_bloqueia(self) -> None:
        achado = _um(parse_texto(COM_ACL_NEGA), "192.168.30.2", "192.168.20.10")
        assert achado.codigo == "TESTE_BLOQUEADO_POR_ACL"
        assert achado.severidade == "erro"

    def test_a_mensagem_cita_a_regra_e_a_linha(self) -> None:
        achado = _um(parse_texto(COM_ACL_NEGA), "192.168.30.2", "192.168.20.10")
        assert "deny ip any any" in achado.mensagem
        assert achado.linha > 0

    def test_permit_sem_deny_deixa_passar(self) -> None:
        # O padrao implicito da ACL e permitir. Um teste que tratasse
        # ausencia de deny como bloqueio reprovaria arquivos corretos.
        config = parse_texto(COM_ROTA + "access-list 100 permit tcp any any eq 22\n")
        assert _um(config, "192.168.30.2", "192.168.20.10").codigo == "TESTE_OK"

    def test_deny_especifico_nao_bloqueia_o_todo(self) -> None:
        config = parse_texto(
            COM_ROTA + "access-list 100 deny ip any any eq 23\n"
        )
        # O laboratorio nao simula inspecao de pacote; so o `deny ip any any`
        # fecha o caminho. Deixar isso explicito evita um falso bloqueio.
        assert _um(config, "192.168.30.2", "192.168.20.10").codigo == "TESTE_OK"


class TestRobustez:
    """O modulo nao quebra com entrada estranha."""

    def test_ip_address_sem_mascara_nao_quebra(self) -> None:
        config = parse_texto("interface Vlan30\n ip address 192.168.30.2\n")
        assert _um(config, "192.168.30.2", "192.168.30.9").codigo

    def test_mascara_invalida_nao_quebra(self) -> None:
        config = parse_texto(
            "interface Vlan30\n ip address 192.168.30.2 999.999.999.999\n"
        )
        assert _um(config, "192.168.30.2", "10.0.0.1").codigo

    def test_rota_truncada_nao_quebra(self) -> None:
        config = parse_texto(
            "interface Vlan30\n"
            " ip address 192.168.30.2 255.255.255.0\n"
            "ip route 192.168.20.0\n"
        )
        assert _um(config, "192.168.30.2", "192.168.20.10").codigo == "TESTE_SEM_CAMINHO"

    def test_config_sem_interface_alguma(self) -> None:
        assert _um(parse_texto("hostname X\n"), "1.2.3.4", "5.6.7.8").codigo == (
            "TESTE_SEM_CAMINHO"
        )

    def test_todos_os_enderecos_do_lab_sao_rfc1918(self) -> None:
        for alvo in testes.alvos_padrao():
            partes = alvo.endereco.split(".")
            assert partes[0] == "192" and partes[1] == "168", alvo.nome


class TestNaoFalaComOMundo:
    """A garantia de que o simulador e local."""

    def test_o_modulo_nao_importa_rede(self) -> None:
        import netci.testes as modulo

        fonte = Path(modulo.__file__).read_text(encoding="utf-8")
        for proibido in ("import socket", "import requests", "import urllib", "subprocess"):
            assert proibido not in fonte, f"o modulo importa {proibido}"

    def test_alvo_tem_endereco_como_texto(self) -> None:
        alvo = testes.Alvo("gerencia", "192.168.30.2")
        assert str(alvo.ip) == "192.168.30.2"


class TestOrm:
    """O contrato com o resto do pipeline."""

    def test_tabela_declara_as_tres_saidas(self) -> None:
        codigos = {r.codigo for r in testes.tabela()}
        assert codigos == {
            "TESTE_SEM_CAMINHO",
            "TESTE_BLOQUEADO_POR_ACL",
            "TESTE_OK",
        }

    def test_achado_tem_estagio_testes(self) -> None:
        achado = _um(parse_texto(GOLDEN.read_text(encoding="utf-8")),
                     "192.168.30.2", "192.168.30.9")
        assert achado.estagio == "testes"

    def test_o_golden_bloqueia_o_proprio_acesso(self) -> None:
        # O golden tem `deny ip any any`, entao qualquer caminho e bloqueado.
        # E o comportamento correto: o filtro de entrada existe para fechar.
        achado = _um(parse_arquivo(GOLDEN), "192.168.30.2", "192.168.30.99")
        assert achado.codigo == "TESTE_BLOQUEADO_POR_ACL"