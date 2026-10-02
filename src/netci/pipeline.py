"""O encadeamento dos cinco estagios.

The chain of the five stages.

Este modulo e o orquestrador: ele decide a ordem, para no primeiro estagio que
reprova, e monta o `Resultado` que o relatorio consome. Nenhum estagio sabe
que os outros existem.

## Por que parar no primeiro

A tentacao e rodar tudo e juntar os erros, achando que um relatorio com sete
problemas e mais util que um com um. E o oposto.

Erro de sintaxe muda a leitura de tudo que vem depois: um `trun` que ninguem
reconhece faz a regra de negocio nao encontrar a porta access que deveria
estar ali, e o relatorio passa a listar como problema de negocio algo que e
consequencia do problema de sintaxe. Quem le esse relatorio corrige o primeiro
erro, roda de novo, so entao ve os outros - e chega ao mesmo lugar com mais
esforco e menos informacao sobre a causa.

## A excecao que prova a regra

O estagio de regras roda mesmo quando o de sintaxe reprova, e isso parece
contradizer o paragrafo acima. Nao contradiz: as duas coisas sao erros
*concorrentes*, nao *dependentes*. A VLAN duplicada existe independente de
qualquer `trun` torto no arquivo. Os dois estao no arquivo, os dois precisam
ser corrigidos, e corrigir um primeiro faz o outro continuar la.

A linha que separa as duas situacoes e simples: **o segundo achado existe
independente do primeiro?** Se sim, vale rodar. Se nao, o segundo e
consequencia e o pipeline para.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import golden, relatorio, regras, sintaxe, testes
from .achado import Achado
from .parser import Configuracao, ErroDeParse, parse_arquivo

# Os quatro estagios de verificacao, na ordem. O quinto - o relatorio - nao
# entra aqui porque ele sempre roda e nao produz achado proprio.
CADEIA: tuple[tuple[str, Callable[[Configuracao], list[Achado]]], ...] = (
    ("sintaxe", sintaxe.validar),
    ("regras", regras.validar),
    ("golden", golden.comparar),
)

# O estagio de conectividade recebe o candidato e a referencia, porque o
# teste e sobre o plano de enderecamento que os dois compartilham.
TESTE = "testes"


def rodar(
    arquivo: str | Path,
    golden_path: str | Path | None = None,
    origem: str | None = None,
    destino: str | None = None,
) -> relatorio.Resultado:
    """Roda o pipeline inteiro sobre um candidato.

    Run the whole pipeline over one candidate.

    Args:
        arquivo: O candidato.
        golden_path: A configuracao de referencia, se houver.
        origem: O nome do alvo de origem, para o teste de conectividade.
        destino: O nome do alvo de destino, para o teste de conectividade.

    Returns:
        O resultado, com a lista de estagios que rodaram.

    Raises:
        ErroDeParse: Se o candidato nao puder ser lido. Arquivo ilegivel nao
            e config invalida: e erro de entrada, e o relatorio de config
            invalida nao teria sentido.
    """
    caminho = str(arquivo)
    config = parse_arquivo(arquivo)
    resultado = relatorio.Resultado(arquivo=caminho)

    referencia: Configuracao | None = None
    if golden_path:
        referencia = parse_arquivo(golden_path)

    for nome, etapa in CADEIA:
        # O estagio de golden recebe a referencia. Sem `--golden` ele nao
# roda: nao ha contra o que comparar, e chamar `comparar` com um
            # argumento so levanta TypeError no meio do pipeline.
        if nome == "golden":
            if referencia is None:
                continue
            achados = etapa(config, referencia)
        else:
            achados = etapa(config)

        resultado.estagios.append((nome, achados))

        # A regra de parada: para se este estagio achou algum ERRO.
        if any(a.bloqueia for a in achados):
            resultado.interrompido_em = nome
            break

    # O teste de conectividade so roda quando os anteriores nao bloquearam:
    # testar rotas de uma config com sintaxe quebrada produz conclusao sobre
    # um equipamento que nao existe.
    quer_teste = bool(origem and destino)
    if resultado.interrompido_em is None and quer_teste:
        resultado.estagios.append(
            (TESTE, testes.testar(config, origem, destino))
        )

    resultado.teste_pedido = quer_teste
    return resultado


def candidatos(pasta: str | Path) -> list[Path]:
    """Os arquivos .cfg de uma pasta, em ordem de nome.

    The .cfg files of a directory, in name order.

    A ordem por nome e o que torna a saida do `pipeline` reproduzivel. Sem
    ela, a ordem seria a do sistema de arquivos e o relatorio mudaria entre
    execucoes na mesma maquina.

    Args:
        pasta: O diretorio.

    Returns:
        Os arquivos, ordenados.
    """
    return sorted(Path(pasta).glob("*.cfg"))


def tabela_de_regras() -> list[tuple[str, str, str]]:
    """Todas as regras do pipeline, por estagio.

    Every rule in the pipeline, by stage.

    Returns:
        Tuplas ``(estagio, codigo, descricao)``.

    Raises:
        ValueError: Se algum estagio nao devolver a tabela no formato que o
            `sintaxe.py` e o `regras.py` usam. Falhar aqui e melhor do que
            um estagio sumir do relatorio em silencio.
    """
    linhas: list[tuple[str, str, str]] = []
    for nome, etapa in (("sintaxe", sintaxe), ("regras", regras), ("golden", golden), ("testes", testes)):
        tabela = etapa.tabela()
        if not tabela:
            raise ValueError(f"o estagio {nome} nao devolveu tabela de regras")
        for regra in tabela:
            codigo = getattr(regra, "codigo", None)
            descricao = getattr(regra, "descricao", None)
            if codigo is None or descricao is None:
                raise ValueError(
                    f"regra do estagio {nome} sem codigo/descricao: {regra!r}"
                )
            linhas.append((nome, codigo, descricao))
    return linhas