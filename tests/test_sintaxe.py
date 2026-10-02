"""Testes do estagio de sintaxe.

Syntax stage tests.

O estagio de sintaxe e o primeiro filtro, e o que decide se os estagios
seguintes tem alguma coisa legitima para ler. Um estagio de sintaxe que deixa
passar garbage faz os estagios seguintes produzirem conclusao sobre uma
configuracao que nao existe.

Metade destes testes existe para o caminho feliz: um arquivo correto tem de
sair **sem nenhum erro**. Uma regra de sintaxe que acusa o arquivo bom nao esta
protegendo, esta atrapalhando.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from netci import sintaxe
from netci.parser import parse_arquivo, parse_texto

RAIZ = Path(__file__).resolve().parent.parent


def _erros(config) -> list:
    return [a for a in sintaxe.validar(config) if a.bloqueia]


def _codigos(config) -> set[str]:
    return {a.codigo for a in sintaxe.validar(config)}


class TestArquivoBom:
    """Um arquivo correto nao pode ser acusado."""

    @pytest.mark.parametrize(
        "nome", ["switch-ok-1", "switch-ok-2", "switch-ok-3"]
    )
    def test_candidato_valido_passa(self, nome: str) -> None:
        config = parse_arquivo(RAIZ / "dados" / "candidatos" / f"{nome}.cfg")
        assert not _erros(config), [a.resumo() for a in _erros(config)]

    def test_golden_passa(self) -> None:
        config = parse_arquivo(RAIZ / "dados" / "golden" / "switch-core.cfg")
        assert not _erros(config)

    def test_config_minima_valida(self) -> None:
        assert not _erros(parse_texto("hostname SW-1\nvlan 10\n"))


class TestComandoDesconhecido:
    """Palavra fora do vocabulario."""

    def test_comando_inventado(self) -> None:
        config = parse_texto("hostname X\nxyzzy agora\n")
        assert "COMANDO_DESCONHECIDO" in _codigos(config)

    def test_a_mensagem_cita_o_comando(self) -> None:
        config = parse_texto("xyzzy agora\n")
        achado = next(a for a in sintaxe.validar(config) if a.codigo == "COMANDO_DESCONHECIDO")
        assert "xyzzy" in achado.mensagem

    def test_o_achado_tem_a_linha(self) -> None:
        achado = next(
            a for a in sintaxe.validar(parse_texto("hostname X\nxyzzy\n")) 
            if a.codigo == "COMANDO_DESCONHECIDO"
        )
        assert achado.linha == 2

    def test_name_apos_vlan_e_aceito(self) -> None:
        # `vlan 10` seguido de `name X` e o jeito normal de nomear uma VLAN.
        # Sem `name` no vocabulario, todo arquivo que nomeia VLAN era reprovado.
        assert not _erros(parse_texto("vlan 10\n name CORPORATIVO\n"))


class TestParametroInvalido:
    """Argumento que deveria ser numero."""

    def test_vlan_com_id_texto(self) -> None:
        config = parse_texto("vlan dez\n")
        assert "PARAMETRO_INVALIDO" in _codigos(config)

    def test_acesso_com_vlan_texto(self) -> None:
        config = parse_texto(
            "interface Gi0/1\n switchport mode access\n switchport access vlan dez\n"
        )
        assert "PARAMETRO_INVALIDO" in _codigos(config)

    def test_acl_com_numero_texto(self) -> None:
        config = parse_texto("access-list cem permit ip any any\n")
        assert "PARAMETRO_INVALIDO" in _codigos(config)

    def test_ip_address_sem_argumentos(self) -> None:
        config = parse_texto("interface Gi0/1\n ip address\n")
        assert not _erros(config), "ip address sem argumento e aviso, nao erro"


class TestValorInvalido:
    """Valor fora da faixa permitida."""

    def test_vlan_acima_do_limite(self) -> None:
        achado = next(
            a for a in sintaxe.validar(parse_texto("vlan 5000\n"))
            if a.codigo == "VALOR_INVALIDO"
        )
        assert "5000" in achado.mensagem

    def test_vlan_zero_e_reservada(self) -> None:
        assert "VALOR_INVALIDO" in _codigos(parse_texto("vlan 0\n"))

    def test_vlan_4095_e_reservada(self) -> None:
        assert "VALOR_INVALIDO" in _codigos(parse_texto("vlan 4095\n"))

    def test_modo_de_porta_invalido(self) -> None:
        config = parse_texto("interface Gi0/1\n switchport mode trun\n")
        assert "VALOR_INVALIDO" in _codigos(config)

    def test_a_sugestao_aponta_a_grafia_certa(self) -> None:
        # O erro mais comum de digitacao em `mode` e `trun` por `trunk`, e a
        # sugestao diz isso. Um relatorio que so diz "valor invalido" obriga o
        # leitor a abrir o arquivo e adivinhar.
        achado = next(
            a for a in sintaxe.validar(parse_texto("interface Gi0/1\n switchport mode trun\n"))
            if a.codigo == "VALOR_INVALIDO"
        )
        assert "trunk" in achado.sugestao

    def test_modo_valido_nao_acusa(self) -> None:
        for modo in ("access", "trunk", "dynamic", "dot1q-tunnel"):
            config = parse_texto(f"interface Gi0/1\n switchport mode {modo}\n")
            assert "VALOR_INVALIDO" not in _codigos(config), modo

    def test_switchport_mode_sem_valor(self) -> None:
        config = parse_texto("interface Gi0/1\n switchport mode\n")
        assert "PARAMETRO_INVALIDO" in _codigos(config)

    def test_acl_fora_da_faixa_padrao_avisa(self) -> None:
        config = parse_texto("access-list 500 permit ip any any\n")
        # ACL fora da faixa padrao e aviso: o equipamento aceita.
        assert not _erros(config)
        assert "VALOR_INVALIDO" in _codigos(config)


class TestRota:
    """A sintaxe de `ip route`."""

    def test_rota_completa_passa(self) -> None:
        config = parse_texto("ip route 192.168.20.0 255.255.255.0 10.0.0.1\n")
        assert not _erros(config)

    def test_rota_truncada(self) -> None:
        config = parse_texto("ip route 192.168.20.0\n")
        achado = next(a for a in sintaxe.validar(config) if a.codigo == "PARAMETRO_INVALIDO")
        assert "proximo" in achado.sugestao

    def test_destino_nao_e_endereco(self) -> None:
        # `route` e a posicao 0 dos argumentos. Se o codigo validar a posicao
        # errada, ele acusa `route` como endereco e reprova no estagio de
        # sintaxe o que e problema de negocio.
        config = parse_texto("ip route naoeumendereco 255.255.255.0 10.0.0.1\n")
        assert "PARAMETRO_INVALIDO" in _codigos(config)

    def test_ip_com_subcomando_desconhecido(self) -> None:
        # A mensagem tem de citar `ip banana`, e nao `ip`: `ip` e um comando
        # valido, e dizer que ele e desconhecido manda o leitor procurar um
        # comando que ele acabou de escrever certo.
        config = parse_texto("ip banana 1.2.3.4\n")
        achado = next(a for a in sintaxe.validar(config) if a.codigo == "COMANDO_DESCONHECIDO")
        assert "ip banana" in achado.mensagem


class TestInterface:
    """Blocos de interface."""

    def test_interface_duplicada(self) -> None:
        config = parse_texto(
            "interface Gi0/1\n description a\n"
            "interface Gi0/1\n description b\n"
        )
        achado = next(
            a for a in sintaxe.validar(config) if a.codigo == "INTERFACE_DUPLICADA"
        )
        assert achado.linha == 3
        assert "linha 1" in achado.sugestao, "a sugestao tem de apontar a primeira"

    def test_interface_vazia_avisa(self) -> None:
        config = parse_texto("interface Gi0/1\ninterface Gi0/2\n")
        assert "INTERFACE_VAZIA" in _codigos(config)
        assert not _erros(config), "interface vazia e aviso, nao erro"

    def test_subcomando_desconhecido_avisa(self) -> None:
        config = parse_texto("interface Gi0/1\n snmp trap link up\n")
        assert "SUBCOMANDO_DESCONHECIDO" in _codigos(config)
        assert not _erros(config)

    def test_blocos_nao_engolem_um_a_outro(self) -> None:
        # Configuracao real nao escreve `exit`. Se a indentacao nao fosse o
        # sinal de bloco, cada interface seria engolida pela anterior.
        config = parse_texto(
            "interface Gi0/1\n description uma\n"
            "interface Gi0/2\n description duas\n"
        )
        assert not _erros(config)


class TestBlocoLinha:
    """Blocos `line vty`."""

    def test_password_e_reconhecido(self) -> None:
        config = parse_texto("line vty 0 4\n password X\n")
        assert not _erros(config), "password dentro de line vty nao e erro"

    def test_transport_e_reconhecido(self) -> None:
        config = parse_texto("line vty 0 4\n transport input ssh\n")
        assert not _erros(config)

    def test_bloco_vazio_avisa(self) -> None:
        config = parse_texto("line vty 0 4\nvlan 10\n")
        assert "BLOCO_LINHA_VAZIO" in _codigos(config)

    def test_subcomando_de_vty_desconhecido_avisa(self) -> None:
        config = parse_texto("line vty 0 4\n snmp timeouts 10\n")
        assert "SUBCOMANDO_DESCONHECIDO" in _codigos(config)


class TestSemHostname:
    """Hostname faltando."""

    def test_sem_hostname_avisa(self) -> None:
        config = parse_texto("vlan 10\n")
        assert "SEM_HOSTNAME" in _codigos(config)
        assert not _erros(config), "sem hostname e aviso, nao erro"

    def test_com_hostname_nao_avisa(self) -> None:
        assert "SEM_HOSTNAME" not in _codigos(parse_texto("hostname X\n"))


class TestOrm:
    """O contrato com o resto do pipeline."""

    def test_tabela_tem_as_sete_regras(self) -> None:
        codigos = {r.codigo for r in sintaxe.tabela()}
        for esperado in (
            "COMANDO_DESCONHECIDO",
            "PARAMETRO_INVALIDO",
            "VALOR_INVALIDO",
            "INTERFACE_DUPLICADA",
            "INTERFACE_VAZIA",
            "SUBCOMANDO_DESCONHECIDO",
            "SEM_HOSTNAME",
        ):
            assert esperado in codigos, esperado

    def test_achado_tem_estagio_sintaxe(self) -> None:
        for a in sintaxe.validar(parse_texto("xyzzy\n")):
            assert a.estagio == "sintaxe"

    def test_achados_ordenados_por_linha(self) -> None:
        config = parse_texto("xyzzy\nvlan 5000\nxyzzy\n")
        achados = sintaxe.validar(config)
        linhas = [a.linha for a in achados if a.linha]
        assert linhas == sorted(linhas)

    def test_codigos_sao_unicos(self) -> None:
        codigos = [r.codigo for r in sintaxe.tabela()]
        assert len(codigos) == len(set(codigos))

    def test_todo_achado_tem_sugestao_quando_cabe(self) -> None:
        # Um achado que nao diz o que fazer obriga o leitor a decidir sozinho,
        # que e o trabalho que o pipeline deveria estar fazendo.
        config = parse_texto("interface Gi0/1\n switchport mode trun\n")
        for a in _erros(config):
            assert a.sugestao, f"{a.codigo} sem sugestao"