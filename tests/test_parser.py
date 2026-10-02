"""Testes do parser.

Parser tests.

O parser e o unico modulo que sabe o que e uma linha de configuracao, e os
tres estagios do pipeline dependem da estrutura que ele produz. Estes testes
fixam os tres jeitos de um arquivo real ser diferente do que o laboratorio
esperava:

1. **bloco sem `exit`**: configuracao de equipamento raramente fecha bloco.
   O sinal de bloco e a indentacao, e nao a palavra `exit`.
2. **`line vty`**: acesso remoto e um bloco como outro qualquer, e sem
   reconhecer isso o `password` vira comando solto.
3. **comentario dentro de bloco**: `!` comenta, nao fecha.
"""

from __future__ import annotations

import pytest

from netci.parser import (
    Comando,
    Configuracao,
    ErroDeParse,
    Interface,
    parse_arquivo,
    parse_texto,
)


class TestBasico:
    """O caminho feliz."""

    def test_comando_simples(self) -> None:
        config = parse_texto("hostname SW-1\n")
        assert len(config.comandos) == 1
        assert config.comandos[0].nome == "hostname"
        assert config.comandos[0].argumentos == "SW-1"
        assert config.comandos[0].linha == 1

    def test_espacos_das_pontas_sao_removidos(self) -> None:
        config = parse_texto("   hostname SW-1   \n")
        assert config.comandos[0].argumentos == "SW-1"

    def test_comentario_e_descartado(self) -> None:
        config = parse_texto("! isto e um comentario\nhostname SW-1\n")
        assert [c.nome for c in config.comandos] == ["hostname"]

    def test_linha_vazia_e_descartada(self) -> None:
        config = parse_texto("\n\n   \nhostname SW-1\n")
        assert len(config.comandos) == 1

    def test_numero_da_linha_preservado(self) -> None:
        config = parse_texto("! comentario\n\nhostname SW-1\nvlan 10\n")
        assert config.comandos[0].linha == 3
        assert config.comandos[1].linha == 4


class TestBlocosDeInterface:
    """Blocos de interface, com e sem `exit`."""

    def test_interface_com_subcomandos(self) -> None:
        config = parse_texto(
            "interface Gi0/1\n"
            " description estacao\n"
            " switchport mode access\n"
        )
        assert len(config.interfaces) == 1
        interface = config.interfaces[0]
        assert interface.nome == "Gi0/1"
        assert [s.nome for s in interface.subcomandos] == ["description", "switchport"]

    def test_interface_sem_exit_encerra_na_indentacao(self) -> None:
        # Configuracao real nao escreve `exit` entre blocos. Sem a
        # indentacao como sinal, cada interface seria engolida pela anterior.
        config = parse_texto(
            "interface Gi0/1\n"
            " description uma\n"
            "interface Gi0/2\n"
            " description duas\n"
        )
        assert [i.nome for i in config.interfaces] == ["Gi0/1", "Gi0/2"]
        assert config.interfaces[0].subcomandos[0].argumentos == "uma"
        assert config.interfaces[1].subcomandos[0].argumentos == "duas"

    def test_exit_explicito_tambem_encerra(self) -> None:
        config = parse_texto(
            "interface Gi0/1\n"
            " description uma\n"
            " exit\n"
            "vlan 10\n"
        )
        assert len(config.interfaces) == 1
        assert [c.nome for c in config.comandos] == ["vlan"]

    def test_comentario_nao_encerra_bloco(self) -> None:
        config = parse_texto(
            "interface Gi0/1\n"
            " ! isto e comentario\n"
            " description uma\n"
        )
        assert [s.nome for s in config.interfaces[0].subcomandos] == ["description"]

    def test_interface_vazia(self) -> None:
        config = parse_texto("interface Gi0/1\ninterface Gi0/2\n")
        assert config.interfaces[0].subcomandos == []


class TestBlocosDeLinha:
    """Blocos `line vty`, o acesso remoto."""

    def test_line_vty_com_password(self) -> None:
        config = parse_texto(
            "line vty 0 4\n"
            " password FICTICIO\n"
            " transport input ssh\n"
        )
        assert len(config.blocos_linha) == 1
        bloco = config.blocos_linha[0]
        assert bloco.tipo == "vty"
        assert bloco.faixa == "0 4"
        assert [s.nome for s in bloco.subcomandos] == ["password", "transport"]

    def test_line_vty_encerra_na_linha_nao_indentada(self) -> None:
        # Sem isto, o `enable secret` depois do `line vty` vira subcomando de
        # linha e some do vocabulario.
        config = parse_texto(
            "line vty 0 4\n"
            " password FICTICIO\n"
            "enable secret FICTICIO\n"
        )
        assert [s.nome for s in config.blocos_linha[0].subcomandos] == ["password"]
        assert [c.nome for c in config.comandos] == ["enable"]

    def test_bloco_vty_acessivel_por_atalho(self) -> None:
        config = parse_texto("line console 0\n exec\nline vty 0 4\n password X\n")
        bloco = config.bloco_vty()
        assert bloco is not None
        assert bloco.faixa == "0 4"

    def test_sem_vty_devolve_none(self) -> None:
        assert parse_texto("hostname X\n").bloco_vty() is None


class TestConsultas:
    """As consultas sobre a configuracao."""

    def _config(self) -> Configuracao:
        return parse_texto(
            "vlan 10 CORP\n"
            "vlan 20\n"
            "vlan 10\n"
            "interface Gi0/1\n"
            " switchport access vlan 10\n"
        )

    def test_por_nome(self) -> None:
        config = self._config()
        assert len(config.por_nome("vlan")) == 3
        assert config.por_nome("inexistente") == []

    def test_declaracoes_vlan(self) -> None:
        config = self._config()
        declaracoes = config.declaracoes_vlan()
        assert declaracoes == [
            (1, 10, "CORP"),
            (2, 20, None),
            (3, 10, None),
        ]

    def test_vlan_nao_numerica_e_ignorada(self) -> None:
        config = parse_texto("vlan dez\n")
        assert config.declaracoes_vlan() == []

    def test_interface_por_nome(self) -> None:
        config = self._config()
        assert config.interface("Gi0/1") is not None
        assert config.interface("Gi0/9") is None

    def test_dentro_de_interface(self) -> None:
        config = self._config()
        assert [s.nome for s in config.dentro_de_interface("Gi0/1")] == ["switchport"]
        assert config.dentro_de_interface("inexistente") == []

    def test_iter_todos_inclui_todos_os_niveis(self) -> None:
        config = parse_texto(
            "vlan 10\n"
            "line vty 0 4\n"
            " password X\n"
            "interface Gi0/1\n"
            " description y\n"
        )
        nomes = [c.nome for c in config.iter_todos()]
        assert "vlan" in nomes
        assert "password" in nomes
        assert "description" in nomes


class TestArgumentos:
    """A leitura de argumentos."""

    def test_tokens(self) -> None:
        comando = Comando(nome="ip", argumentos="route 10.0.0.0 255.0.0.0 1.1.1.1", linha=1)
        assert comando.tokens() == ["route", "10.0.0.0", "255.0.0.0", "1.1.1.1"]

    def test_valor_por_posicao(self) -> None:
        comando = Comando(nome="vlan", argumentos="10", linha=1)
        assert comando.valor(0) == "10"
        assert comando.valor(9) is None

    def test_inteiro(self) -> None:
        assert Comando(nome="v", argumentos="10", linha=1).inteiro(0) == 10
        assert Comando(nome="v", argumentos="dez", linha=1).inteiro(0) is None
        assert Comando(nome="v", argumentos="", linha=1).inteiro(0) is None


class TestArquivo:
    """A leitura de disco."""

    def test_arquivo_inexistente(self, tmp_path) -> None:
        with pytest.raises(ErroDeParse):
            parse_arquivo(tmp_path / "nao-existe.cfg")

    def test_arquivo_valido(self, tmp_path) -> None:
        caminho = tmp_path / "x.cfg"
        caminho.write_text("hostname SW-1\nvlan 10\n", encoding="utf-8")
        config = parse_arquivo(caminho)
        assert config.caminho == str(caminho)
        assert len(config.comandos) == 2

    def test_arquivo_que_nao_e_utf8(self, tmp_path) -> None:
        caminho = tmp_path / "x.cfg"
        caminho.write_bytes(b"hostname \xff\xfe\n")
        with pytest.raises(ErroDeParse):
            parse_arquivo(caminho)

    def test_arquivo_vazio(self, tmp_path) -> None:
        caminho = tmp_path / "vazio.cfg"
        caminho.write_text("", encoding="utf-8")
        config = parse_arquivo(caminho)
        assert config.comandos == []
        assert config.interfaces == []


class TestOsArquivosDoProjeto:
    """Os arquivos reais do projeto tem de ser coerentes entre si."""

    def test_golden_tem_o_que_o_golden_espera(self) -> None:
        config = parse_arquivo("dados/golden/switch-core.cfg")
        assert config.por_nome("enable")
        assert config.bloco_vty() is not None
        assert config.por_nome("spanning-tree")
        assert config.interface("Gi0/1") is not None

    def test_golden_nao_tem_erro_de_parsing(self) -> None:
        # Nenhum comando do golden pode sobrar sem parse por causa do parser: um comando solto
        # aqui significa que o parser errou a estrutura, e o primeiro estagio
        # vai acusar arquivo correto como invalido.
        from netci import sintaxe

        config = parse_arquivo("dados/golden/switch-core.cfg")
        erros = [a for a in sintaxe.validar(config) if a.bloqueia]
        assert not erros, [a.mensagem for a in erros]

    def test_candidatos_validos_passam_de_sintaxe(self) -> None:
        from netci import sintaxe

        for nome in ("switch-ok-1", "switch-ok-2", "switch-ok-3"):
            config = parse_arquivo(f"dados/candidatos/{nome}.cfg")
            erros = [a for a in sintaxe.validar(config) if a.bloqueia]
            assert not erros, f"{nome}: {[a.mensagem for a in erros]}"

    def test_candidato_com_erro_de_sintaxe_e_achado(self) -> None:
        from netci import sintaxe

        config = parse_arquivo("dados/candidatos/switch-ruins-sintaxe.cfg")
        erros = [a for a in sintaxe.validar(config) if a.bloqueia]
        assert any(a.codigo == "VALOR_INVALIDO" for a in erros)