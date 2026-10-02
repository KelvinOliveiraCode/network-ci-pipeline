"""Testes do pipeline, do relatorio e da CLI.

Pipeline, report and CLI tests.

Estes tres modulos sao a superficie que o usuario ve, e estavam sem teste
nenhum. A suite anterior provava que as funcoes de validacao funcionam; ela
nao provava que o pipeline as chama na ordem certa, nem que o relatorio diz o
que deveria dizer, nem que o codigo de saida reflete o veredito.

O motivo de isso importar: os tres lugares onde um bug passa despercebido sao
a ordem das chamadas, a formatacao do relatorio e o `return` da CLI. Um erro
em qualquer um deles deixa as funcoes testes em paz.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from netci import pipeline, relatorio
from netci.achado import ERRO, Achado
from netci.cli import main as cli_main

RAIZ = Path(__file__).resolve().parent.parent
GOLDEN = RAIZ / "dados" / "golden" / "switch-core.cfg"
CANDIDATOS = RAIZ / "dados" / "candidatos"

OK_1 = CANDIDATOS / "switch-ok-1.cfg"
RUINS_SINTAXE = CANDIDATOS / "switch-ruins-sintaxe.cfg"
RUINS_REGRAS = CANDIDATOS / "switch-ruins-regras.cfg"


def _sem_saida(funcao, *args, **kwargs):
    """Roda uma funcao capturing stdout.

    Run a function capturing stdout.

    Args:
        funcao: A funcao.
        *args: Argumentos posicionais.
        **kwargs: Argumentos nomeados.

    Returns:
        O par ``(retorno, stdout)``.
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        retorno = funcao(*args, **kwargs)
    return retorno, buffer.getvalue()


class TestPipeline:
    """A ordem dos estagios e a regra de parada."""

    def test_aprovado_roda_os_tres_estagios(self) -> None:
        resultado = pipeline.rodar(OK_1, golden_path=GOLDEN)
        assert [n for n, _ in resultado.estagios] == ["sintaxe", "regras", "golden"]
        assert resultado.interrompido_em is None

    def test_reprovado_na_sintaxe_para_ali(self) -> None:
        resultado = pipeline.rodar(RUINS_SINTAXE, golden_path=GOLDEN)
        assert [n for n, _ in resultado.estagios] == ["sintaxe"]
        assert resultado.interrompido_em == "sintaxe"

    def test_reprovado_nas_regras_para_ali(self) -> None:
        resultado = pipeline.rodar(RUINS_REGRAS, golden_path=GOLDEN)
        assert [n for n, _ in resultado.estagios] == ["sintaxe", "regras"]
        assert resultado.interrompido_em == "regras"

    def test_sem_golden_pula_o_estagio(self) -> None:
        resultado = pipeline.rodar(OK_1)
        assert "golden" not in [n for n, _ in resultado.estagios]

    def test_o_arquivo_vai_no_resultado(self) -> None:
        assert pipeline.rodar(OK_1).arquivo == str(OK_1)

    def test_arquivo_inexistente(self) -> None:
        from netci.parser import ErroDeParse

        with pytest.raises(ErroDeParse):
            pipeline.rodar(RAIZ / "dados" / "candidatos" / "nao-existe.cfg")

    def test_candidatos_ordenados_por_nome(self) -> None:
        # A ordem tem de ser estavel: sem ela, o relatorio do pipeline muda
        # entre execucoes na mesma maquina.
        lista = pipeline.candidatos(CANDIDATOS)
        assert lista == sorted(lista)
        assert len(lista) == 5

    def test_tabela_de_regras_tem_os_quatro_estagios(self) -> None:
        estagios = {nome for nome, _, _ in pipeline.tabela_de_regras()}
        assert estagios == {"sintaxe", "regras", "golden", "testes"}


class TestRelatorio:
    """O texto e o JSON do relatorio."""

    def _resultado_aprovado(self):
        return pipeline.rodar(OK_1, golden_path=GOLDEN)

    def _resultado_reprovado(self):
        return pipeline.rodar(RUINS_REGRAS, golden_path=GOLDEN)

    def test_status_aprovado(self) -> None:
        assert self._resultado_aprovado().status() == "APROVADO"

    def test_status_reprovado(self) -> None:
        assert self._resultado_reprovado().status() == "REPROVADO"

    def test_status_com_avisos(self) -> None:
        resultado = pipeline.rodar(CANDIDATOS / "switch-ok-2.cfg", golden_path=GOLDEN)
        assert resultado.status() == "APROVADO COM AVISOS"

    def test_texto_tem_o_nome_do_arquivo(self) -> None:
        assert "switch-ok-1.cfg" in relatorio.texto(self._resultado_aprovado())

    def test_texto_marca_o_estagio_que_parou(self) -> None:
        texto = relatorio.texto(self._resultado_reprovado())
        assert "INTERROMPIDO EM: regras" in texto

    def test_texto_distingue_nao_rodou_de_nao_solicitado(self) -> None:
        # Sem esta distincao o relatorio afirma que o pipeline parou num
        # estagio que passou, e quem le conclui que o teste de conectividade
        # foi verificado quando nao foi.
        resultado = pipeline.rodar(OK_1, golden_path=GOLDEN)
        texto = relatorio.texto(resultado)
        assert "nao solicitado" in texto
        assert "estagio anterior reprovou" not in texto

    def test_texto_diz_que_parou_quando_parou(self) -> None:
        texto = relatorio.texto(self._resultado_reprovado())
        # Aqui o estagio de teste realmente nao rodou porque o anterior
        # reprovou, e e isso que o relatorio tem que dizer.
        assert "estagio anterior reprovou" in texto

    def test_texto_marca_os_estagios_que_nao_rodaram(self) -> None:
        # Um estagio que nao rodou e diferente de um que passou. Sem a marca,
        # o relatorio deixa o usuario sem saber se o resto foi verificado.
        texto = relatorio.texto(self._resultado_reprovado())
        assert "nao rodou" in texto

    def test_texto_mostra_a_linha_do_achado(self) -> None:
        resultado = self._resultado_reprovado()
        primeiro = next(a for a in resultado.achados if a.linha)
        assert f"linha {primeiro.linha}" in relatorio.texto(resultado)

    def test_texto_mostra_o_codigo_da_regra(self) -> None:
        assert "VLAN_DUPLICADA" in relatorio.texto(self._resultado_reprovado())

    def test_texto_nao_tem_achado_quando_passa(self) -> None:
        assert "ACHADOS" not in relatorio.texto(self._resultado_aprovado())

    def test_erro_vem_antes_de_aviso(self) -> None:
        # Quem tem 40 avisos e 1 erro precisa ver o erro primeiro.
        resultado = relatorio.Resultado(
            arquivo="x.cfg",
            estagios=[
                ("regras", [
                    Achado("regras", "aviso", "AVISO_A", "aviso", 1),
                    Achado("regras", ERRO, "ERRO_A", "erro", 9),
                ])
            ],
        )
        linhas = [l for l in relatorio.texto(resultado).splitlines() if "[ERRO" in l or "[AVISO" in l]
        assert "ERRO_A" in linhas[0]

    def test_json_tem_a_informacao_completa(self, tmp_path: Path) -> None:
        destino = relatorio.salvar_json(self._resultado_reprovado(), tmp_path / "r.json")
        dados = json.loads(destino.read_text(encoding="utf-8"))
        assert dados["bloqueia"] is True
        assert dados["interrompido_em"] == "regras"
        assert dados["arquivo"].endswith("switch-ruins-regras.cfg")
        assert any(a["codigo"] == "VLAN_DUPLICADA" for a in dados["achados"])
        # Todo achado precisa trazer os seis campos, ou quem consome o JSON
        # tem que adivinhar.
        for achado in dados["achados"]:
            assert set(achado) == {
                "estagio", "severidade", "codigo", "mensagem", "linha", "sugestao"
            }

    def test_json_marca_cada_estagio(self, tmp_path: Path) -> None:
        destino = relatorio.salvar_json(self._resultado_reprovado(), tmp_path / "r.json")
        dados = json.loads(destino.read_text(encoding="utf-8"))
        rodados = [e["nome"] for e in dados["estagios"]]
        assert rodados == ["sintaxe", "regras"]

    def test_resumo_curto_uma_linha(self) -> None:
        linha = relatorio.resumo_curto(self._resultado_reprovado())
        assert "\n" not in linha
        assert "REPROVADO" in linha


class TestCli:
    """A linha de comando e o codigo de saida."""

    def test_validar_aprovado_saida_zero(self) -> None:
        codigo, _ = _sem_saida(
            cli_main, ["validar", str(OK_1), "--golden", str(GOLDEN)]
        )
        assert codigo == 0

    def test_validar_reprovado_saida_um(self) -> None:
        codigo, saida = _sem_saida(
            cli_main, ["validar", str(RUINS_SINTAXE), "--golden", str(GOLDEN)]
        )
        assert codigo == 1
        assert "REPROVADO" in saida

    def test_validar_imprime_a_saida_real(self) -> None:
        _, saida = _sem_saida(
            cli_main, ["validar", str(RUINS_REGRAS), "--golden", str(GOLDEN)]
        )
        assert "VLAN_DUPLICADA" in saida
        assert "INTERROMPIDO" in saida

    def test_validar_gera_json(self, tmp_path: Path) -> None:
        destino = tmp_path / "r.json"
        _sem_saida(
            cli_main,
            ["validar", str(OK_1), "--golden", str(GOLDEN), "--json", str(destino)],
        )
        assert destino.exists()
        assert json.loads(destino.read_text(encoding="utf-8"))["bloqueia"] is False

    def test_validar_com_teste_de_conectividade(self) -> None:
        codigo, saida = _sem_saida(
            cli_main,
            [
                "validar", str(OK_1), "--golden", str(GOLDEN),
                "--origem", "192.168.30.2", "--destino", "192.168.30.9",
            ],
        )
        assert "TESTE_BLOQUEADO_POR_ACL" in saida
        assert codigo == 1

    def test_arquivo_inexistente_saida_dois(self, tmp_path: Path) -> None:
        codigo = cli_main(["validar", str(tmp_path / "nao-existe.cfg")])
        assert codigo == 2

    def test_pipeline_saida_um_quando_ha_reprovado(self) -> None:
        codigo, saida = _sem_saida(
            cli_main, ["pipeline", str(CANDIDATOS), "--golden", str(GOLDEN)]
        )
        assert codigo == 1
        assert "3 aprovado(s), 2 reprovado(s)" in saida

    def test_pipeline_mostra_o_veredito_de_todos(self) -> None:
        _, saida = _sem_saida(
            cli_main, ["pipeline", str(CANDIDATOS), "--golden", str(GOLDEN)]
        )
        for nome in ("switch-ok-1.cfg", "switch-ok-2.cfg", "switch-ok-3.cfg",
                     "switch-ruins-sintaxe.cfg", "switch-ruins-regras.cfg"):
            assert nome in saida

    def test_pipeline_pasta_vazia(self, tmp_path: Path) -> None:
        codigo = cli_main(["pipeline", str(tmp_path)])
        assert codigo == 2

    def test_regras_lista_os_quatro_estagios(self) -> None:
        codigo, saida = _sem_saida(cli_main, ["regras"])
        assert codigo == 0
        for estagio in ("sintaxe", "regras", "golden", "testes"):
            assert estagio in saida

    def test_regras_filtra_por_estagio(self) -> None:
        _, saida = _sem_saida(cli_main, ["regras", "--estagio", "testes"])
        assert "TESTE_OK" in saida
        assert "VLAN_DUPLICADA" not in saida

    def test_sem_comando_falha(self) -> None:
        with pytest.raises(SystemExit):
            cli_main([])

    def test_help_sai_com_zero(self, capsys) -> None:
        with pytest.raises(SystemExit) as erro:
            cli_main(["--help"])
        assert erro.value.code == 0

    @pytest.mark.parametrize("comando", ["validar", "pipeline", "regras"])
    def test_help_de_cada_comando(self, comando: str) -> None:
        with pytest.raises(SystemExit) as erro:
            cli_main([comando, "--help"])
        assert erro.value.code == 0