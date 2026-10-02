"""A linha de comando do netci.

The netci command line.

Tres comandos:

- `validar` - roda os estagios em um candidato. E o comando principal.
- `pipeline` - roda todos os candidatos de uma pasta e mostra o veredito de
  cada um lado a lado.
- `regras` - mostra as regras de cada estagio com a severidade.

O codigo de saida segue uma regra simples: **0 quando o candidato pode ir
para o merge, diferente de zero quando nao pode**. E o que permite
`netci validar` ser o unico comando de um job de CI, sem wrapper em volta.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import pipeline as modulo_pipeline
from . import relatorio as modulo_relatorio
from .achado import AVISO, ERRO
from .parser import ErroDeParse

SAIDA_OK = 0
SAIDA_REPROVADO = 1
SAIDA_ERRO = 2


def _constroi_parser() -> argparse.ArgumentParser:
    """Monta o parser de argumentos.

    Build the argument parser.

    Returns:
        O parser pronto.
    """
    parser = argparse.ArgumentParser(
        prog="netci",
        description=(
            "Pipeline local de CI para configuracao de rede ficticia. "
            "Valida antes de aplicar; nao aplica nada. / "
            "Local CI pipeline for fictitious network configuration."
        ),
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_validar = sub.add_parser(
        "validar",
        help="valida um candidato",
        description="Roda os estagios em um candidato e para no primeiro que reprova.",
    )
    p_validar.add_argument("arquivo", help="configuracao a validar")
    p_validar.add_argument("--golden", help="configuracao de referencia")
    p_validar.add_argument("--origem", help="alvo de origem do teste de conectividade")
    p_validar.add_argument("--destino", help="alvo de destino do teste de conectividade")
    p_validar.add_argument("--json", help="grava o resultado em JSON neste caminho")

    p_pipeline = sub.add_parser(
        "pipeline",
        help="valida todos os candidatos de uma pasta",
        description="Valida todos os .cfg de uma pasta e mostra o veredito de cada um.",
    )
    p_pipeline.add_argument("pasta", nargs="?", default="dados/candidatos")
    p_pipeline.add_argument("--golden", default="dados/golden/switch-core.cfg")
    p_pipeline.add_argument("--origem", help="alvo de origem do teste de conectividade")
    p_pipeline.add_argument("--destino", help="alvo de destino do teste de conectividade")
    p_pipeline.add_argument("--json", help="grava o resultado geral em JSON")

    p_regras = sub.add_parser(
        "regras",
        help="mostra as regras por estagio",
        description="Lista as regras que o pipeline avalia, por estagio.",
    )
    p_regras.add_argument("--estagio", help="filtra por estagio")

    return parser


def _cmd_validar(args: argparse.Namespace, destino) -> int:
    """Executa `validar`.

    Run `validar`.

    Args:
        args: Os argumentos.
        destino: Onde imprimir.

    Returns:
        O codigo de saida.
    """
    resultado = modulo_pipeline.rodar(
        args.arquivo,
        golden_path=args.golden,
        origem=args.origem,
        destino=args.destino,
    )
    print(modulo_relatorio.texto(resultado), file=destino)

    if args.json:
        modulo_relatorio.salvar_json(resultado, args.json)
        print(f"\njson: {args.json}", file=destino)

    if resultado.passou:
        return SAIDA_OK
    if resultado.bloqueia:
        return SAIDA_REPROVADO
    # Passou com avisos: nao bloqueia o merge, mas o codigo ainda e zero.
    return SAIDA_OK


def _cmd_pipeline(args: argparse.Namespace, destino) -> int:
    """Executa `pipeline`.

    Run `pipeline`.

    Args:
        args: Os argumentos.
        destino: Onde imprimir.

    Returns:
        0 se todos passaram, 1 se algum foi reprovado.
    """
    pasta = Path(args.pasta)
    arquivos = modulo_pipeline.candidatos(pasta)

    if not arquivos:
        print(f"nenhum .cfg encontrado em {pasta}", file=sys.stderr)
        return SAIDA_ERRO

    resultados = []
    for arquivo in arquivos:
        resultados.append(
            modulo_pipeline.rodar(
                arquivo,
                golden_path=args.golden,
                origem=args.origem,
                destino=args.destino,
            )
        )

    # Cabecalho com o veredito de lado a lado: e a leitura que um recrutador
    # quer, antes de qualquer detalhe.
    print("=" * 72, file=destino)
    print(f"PIPELINE DE {len(resultados)} CANDIDATO(S)", file=destino)
    print("=" * 72, file=destino)

    for resultado in resultados:
        print(
            f"{resultado.status():<20} "
            f"{resultado.contar(ERRO)} erro(s)  "
            f"{resultado.contar(AVISO)} aviso(s)  "
            f"{Path(resultado.arquivo).name}",
            file=destino,
        )

    print("", file=destino)

    # Depois, o detalhe de cada um que reprovou. Os aprovados entram em uma
    # linha, porque nao ha nada a ler sobre eles.
    for resultado in resultados:
        if resultado.passou:
            continue
        print(modulo_relatorio.texto(resultado), file=destino)
        print("", file=destino)

    reprovados = [r for r in resultados if r.bloqueia]
    print("=" * 72, file=destino)
    print(
        f"{len(resultados) - len(reprovados)} aprovado(s), {len(reprovados)} reprovado(s)",
        file=destino,
    )

    if args.json:
        modulo_relatorio.salvar_json(
            _resultado_geral(resultados), args.json
        )
        print(f"json: {args.json}", file=destino)

    return SAIDA_REPROVADO if reprovados else SAIDA_OK


def _resultado_geral(resultados):
    """Junta os resultados em um so, para o JSON.

    Merge the results into one, for the JSON.

    Args:
        resultados: Os resultados individuais.

    Returns:
        O resultado agregado, com os estagios de todos.
    """
    agregado = modulo_relatorio.Resultado(arquivo="pipeline")
    for resultado in resultados:
        agregado.estagios.extend(resultado.estagios)
        if resultado.interrompido_em and not agregado.interrompido_em:
            agregado.interrompido_em = resultado.interrompido_em
    return agregado


def _cmd_regras(args: argparse.Namespace, destino) -> int:
    """Executa `regras`.

    Run `regras`.

    Args:
        args: Os argumentos.
        destino: Onde imprimir.

    Returns:
        Sempre 0.
    """
    linhas = modulo_pipeline.tabela_de_regras()
    estagio_atual = None
    for estagio, codigo, descricao in linhas:
        if args.estagio and estagio != args.estagio:
            continue
        if estagio != estagio_atual:
            print(f"\n{estagio}:", file=destino)
            estagio_atual = estagio
        print(f"  {codigo:<28} {descricao}", file=destino)
    print(f"\n{len(linhas)} regra(s) no pipeline", file=destino)
    return SAIDA_OK


def main(argv: list[str] | None = None) -> int:
    """O ponto de entrada.

    The entry point.

    Args:
        argv: Os argumentos, sem `argv[0]`. `None` usa `sys.argv`.

    Returns:
        O codigo de saida do processo.
    """
    parser = _constroi_parser()
    args = parser.parse_args(argv)

    try:
        if args.comando == "validar":
            return _cmd_validar(args, sys.stdout)
        if args.comando == "pipeline":
            return _cmd_pipeline(args, sys.stdout)
        if args.comando == "regras":
            return _cmd_regras(args, sys.stdout)
    except ErroDeParse as erro:
        print(f"erro de leitura: {erro}", file=sys.stderr)
        return SAIDA_ERRO
    except ValueError as erro:
        print(f"erro de pipeline: {erro}", file=sys.stderr)
        return SAIDA_ERRO

    parser.error(f"comando desconhecido: {args.comando}")
    return SAIDA_ERRO