"""Prova de aceite do netci.

netci acceptance proof.

O criterio de aceite do projeto tem duas metades:

1. **Os cinco candidatos sao classificados corretamente**, com os dois ruins
   reprovados por motivos **distintos**. "Distintos" e a parte que importa: um
   pipeline que reprova os dois no mesmo estagio por acidente nao esta
   separando sintaxe de negocio, e o criterio nao teria sido provado.
2. **O codigo de saida reflete o resultado.** Um pipeline que reprova e devolve
   zero e pior do que um pipeline sem estagios, porque o merge passa.

O script verifica ainda que a regra de parada funciona - que estagios depois do
primeiro que reprova **nao rodaram**, e aparecem marcados no relatorio. E a
parte que a suite nao prova sozinha: a suite verifica as funcoes, e nao a
ordem em que o pipeline as chama.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from netci import pipeline as modulo_pipeline  # noqa: E402
from netci.cli import main as cli_main  # noqa: E402

GOLDEN = RAIZ / "dados" / "golden" / "switch-core.cfg"
CANDIDATOS = RAIZ / "dados" / "candidatos"

# O veredito que o criterio de aceite exige de cada candidato, e o estagio em
# que ele tem de reprovar. A tabela esta escrita aqui, e nao deduzida do
# codigo, para que o script seja um judge e nao um espelho.
ESPERADO = {
    "switch-ok-1.cfg": (True, None),
    "switch-ok-2.cfg": (True, None),
    "switch-ok-3.cfg": (True, None),
    "switch-ruins-sintaxe.cfg": (False, "sintaxe"),
    "switch-ruins-regras.cfg": (False, "regras"),
}


class Falha(Exception):
    """Uma condicao de aceite nao foi satisfeita."""


def checar(condicao: bool, mensagem: str) -> None:
    """Falha se a condicao e falsa.

    Fail if the condition is false.

    Args:
        condicao: A condicao.
        mensagem: O que deu errado, se ela for falsa.

    Raises:
        Falha: Se a condicao for falsa.
    """
    if not condicao:
        raise Falha(mensagem)


def test_classificacao() -> None:
    """Os cinco candidatos sao classificados como o criterio espera.

    The five candidates are classified as the criterion expects.

    Raises:
        Falha: Se algum veredito divergir.
    """
    print("1) os cinco candidatos tem o veredito esperado")
    resultados = {}
    for nome, (deve_passar, estagio) in sorted(ESPERADO.items()):
        arquivo = CANDIDATOS / nome
        checar(arquivo.exists(), f"{nome}: nao existe em dados/candidatos")
        resultado = modulo_pipeline.rodar(arquivo, golden_path=GOLDEN)
        resultados[nome] = resultado

        passou = resultado.passou
        if passou != deve_passar:
            raise Falha(
                f"{nome}: esperado {'APROVADO' if deve_passar else 'REPROVADO'}, "
                f"veio {resultado.status()} "
                f"({[a.resumo() for a in resultado.achados if a.bloqueia]})"
            )

        if estagio is not None:
            if resultado.interrompido_em != estagio:
                raise Falha(
                    f"{nome}: esperado reprovar em '{estagio}', "
                    f"parou em '{resultado.interrompido_em}'"
                )

        rotulo = "APROVADO" if passou else f"REPROVADO em {resultado.interrompido_em}"
        print(f"   {nome:<28} {rotulo}")

    return resultados


def test_motivos_distintos(resultados) -> None:
    """Os dois reprovados falham por motivos diferentes.

    The two rejected candidates fail for different reasons.

    Este e o coracao do criterio. Dois arquivos reprovados no mesmo estagio
    por regras diferentes provam que o estagio pega mais de um problema; dois
    arquivos reprovados no mesmo estagio pela mesma regra provam que o
    estagio pega um problema, duas vezes.

    Args:
        resultados: Os resultados do pipeline.

    Raises:
        Falha: Se os motivos se sobrepoerem demais.
    """
    print("\n2) os dois reprovados falham por motivos distintos")
    codigos = {}
    for nome, resultado in resultados.items():
        if resultado.passou:
            continue
        codigos[nome] = {a.codigo for a in resultado.achados if a.bloqueia}
        print(f"   {nome}: {sorted(codigos[nome])}")

    reprovados = list(codigos)
    checar(len(reprovados) == 2, f"esperava 2 reprovados, vieram {len(reprovados)}")

    em_comum = codigos[reprovados[0]] & codigos[reprovados[1]]
    checar(
        not em_comum,
        f"os dois reprovados compartilham os codigos {sorted(em_comum)}; "
        "motivos nao sao distintos",
    )


def test_regra_de_parada(resultados) -> None:
    """Depois do primeiro estagio que reprova, nenhum outro roda.

    After the first failing stage, no other one runs.

    Args:
        resultados: Os resultados do pipeline.

    Raises:
        Falha: Se algum estagio rodou depois da parada.
    """
    print("\n3) a regra de parada: estagios depois da falha nao rodam")
    for nome, resultado in resultados.items():
        if resultado.interrompido_em is None:
            continue

        ordem = [n for n, _ in resultado.estagios]
        checar(
            ordem[-1] == resultado.interrompido_em,
            f"{nome}: parou em '{resultado.interrompido_em}' mas o ultimo "
            f"estagio executado foi '{ordem[-1]}'",
        )
        print(f"   {nome}: rodou {ordem}, parou em {resultado.interrompido_em}")


def test_codigo_de_saida() -> None:
    """O codigo de saida reflete o veredito.

    The exit code reflects the verdict.

    Raises:
        Falha: Se algum codigo divergir do esperado.
    """
    print("\n4) o codigo de saida reflete o veredito")
    casos = (
        ("switch-ok-1.cfg", 0),
        ("switch-ok-2.cfg", 0),
        ("switch-ruins-sintaxe.cfg", 1),
        ("switch-ruins-regras.cfg", 1),
    )
    import contextlib
    import io

    for nome, esperado in casos:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            codigo = cli_main([
                "validar",
                str(CANDIDATOS / nome),
                "--golden",
                str(GOLDEN),
            ])
        checar(
            codigo == esperado,
            f"{nome}: codigo de saida {codigo}, esperado {esperado}",
        )
        print(f"   {nome:<28} saida={codigo}")

    # O pipeline inteiro tem de sair != 0 porque ha reprovados no conjunto.
    with contextlib.redirect_stdout(io.StringIO()):
        codigo_pipeline = cli_main([
            "pipeline", str(CANDIDATOS), "--golden", str(GOLDEN)
        ])
    checar(
        codigo_pipeline == 1,
        f"o pipeline dos 5 candidatos deveria sair com 1, saiu com {codigo_pipeline}",
    )
    print(f"   pipeline completo                saida={codigo_pipeline}")


def principal() -> int:
    """Roda a prova de aceite.

    Run the acceptance proof.

    Returns:
        0 se tudo passar, 1 se alguma condicao falhar.
    """
    try:
        resultados = test_classificacao()
        test_motivos_distintos(resultados)
        test_regra_de_parada(resultados)
        test_codigo_de_saida()
    except Falha as erro:
        print("\nACEITE FALHOU:")
        print(f"  - {erro}")
        return 1

    print(
        "\nok: os 5 candidatos classificados certo, os 2 reprovados por motivos "
        "distintos, parada no primeiro estagio que falha, e codigo de saida "
        "correto"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())