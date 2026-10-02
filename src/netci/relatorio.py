"""Estagio 5: o relatorio.

Stage 5: the report.

O relatorio e o unico estagio que roda **sempre**. Os outros quatro param no
primeiro que reprova; este roda depois, com o que ja se sabe, e e ele que
explica ao usuario o que aconteceu.

## Por que texto e nao JSON

O relatorio tem dois leitores com requisitos opostos: a pessoa que le no
terminal e o script que decide se o merge pode ir. Servir os dois com um
formato so significa escolher um lado e quebrar o outro.

A solucao e **os dois, em arquivos diferentes**. O texto vai para o stdout, e
e optimized para ser lido por gente, em ordem de gravidade, com o numero de
linha. O JSON vai para um arquivo, e tem a informacao completa, com a
severidade de cada achado, para quem precisar consultar.

O que **nao** existe e o meio termo: um JSON em stdout legivel por gente e um
textoParsing. Quem precisa dos dois chama os dois.

## A ordem do relatorio

Severidade primeiro, linha depois. Nao e estetica: quem tem um pipeline
vermelho com 40 avisos e 1 erro precisa ver o erro primeiro, e precisa ver a
linha antes de sair procurando.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .achado import AVISO, ERRO, Achado, avisos, erros

# Os estagios, na ordem em que o pipeline os executa. A ordem do relatorio
# e a ordem do pipeline, e nao alfabetica: quem le o relatorio quer a ordem
# em que as coisas foram descobertas.
ESTAGIOS = ("sintaxe", "regras", "golden", "testes")


@dataclass
class Resultado:
    """O resultado de rodar o pipeline inteiro.

    The result of running the whole pipeline.

    Attributes:
        arquivo: O candidato validado.
        estagios: Os estagios que rodaram, na ordem, com os achados de cada um.
        interrompido_em: O estagio que reprovou, ou `None` se todos passaram.
        teste_pedido: Se o teste de conectividade foi solicitado. Um estagio
            que nao rodou por nao ter sido pedido e completamente diferente de
            um que nao rodou porque o anterior reprovou, e o relatorio precisa
            distinguir os dois.
    """

    arquivo: str
    estagios: list[tuple[str, list[Achado]]] = field(default_factory=list)
    interrompido_em: str | None = None
    teste_pedido: bool = False

    @property
    def achados(self) -> list[Achado]:
        """Todos os achados, de todos os estagios que rodaram.

        All findings, from every stage that ran.
        """
        return [a for _, lista in self.estagios for a in lista]

    @property
    def bloqueia(self) -> bool:
        """Se o candidato foi reprovado.

        Whether the candidate was rejected.
        """
        return bool(erros(self.achados))

    @property
    def passou(self) -> bool:
        """Se o candidato passou em tudo.

        Whether the candidate passed everything.
        """
        return not self.bloqueia and self.interrompido_em is None

    def contar(self, severidade: str) -> int:
        """Quantos achados de uma severidade.

        How many findings of a severity.

        Args:
            severidade: `ERRO` ou `AVISO`.

        Returns:
            A quantidade.
        """
        return sum(1 for a in self.achados if a.severidade == severidade)

    def status(self) -> str:
        """O resultado em uma palavra.

        The result in one word.

        Returns:
            `REPROVADO`, `APROVADO COM AVISOS` ou `APROVADO`.
        """
        if self.bloqueia:
            return "REPROVADO"
        if self.contar(AVISO):
            return "APROVADO COM AVISOS"
        return "APROVADO"

    def para_dict(self) -> dict[str, object]:
        """O resultado como dicionario, para JSON.

        The result as a dictionary, for JSON.

        Returns:
            O dicionario completo, com a ordem dos achados preservada.
        """
        return {
            "arquivo": self.arquivo,
            "status": self.status(),
            "bloqueia": self.bloqueia,
            "interrompido_em": self.interrompido_em,
            "estagios": [
                {
                    "nome": nome,
                    "rodou": True,
                    "erros": sum(1 for a in achados_ if a.severidade == ERRO),
                    "avisos": sum(1 for a in achados_ if a.severidade == AVISO),
                }
                for nome, achados_ in self.estagios
            ],
            "achados": [
                {
                    "estagio": a.estagio,
                    "severidade": a.severidade,
                    "codigo": a.codigo,
                    "mensagem": a.mensagem,
                    "linha": a.linha,
                    "sugestao": a.sugestao,
                }
                for a in self.achados
            ],
        }


def _linha_regra(codigo: str, severidade: str) -> str:
    """A linha de um codigo, alinhada em duas colunas.

    A code's line, aligned in two columns.

    Args:
        codigo: O codigo do achado.
        severidade: `ERRO` ou `AVISO`.

    Returns:
        A linha formatada.
    """
    marca = "ERRO " if severidade == ERRO else "AVISO"
    return f"  [{marca}] {codigo}"


def texto(resultado: Resultado) -> str:
    """O relatorio em texto, para o terminal.

    The report as text, for the terminal.

    Args:
        resultado: O resultado do pipeline.

    Returns:
        O relatorio.
    """
    partes: list[str] = [
        "=" * 72,
        f"CI DE REDE - {resultado.arquivo}",
        "=" * 72,
        "",
    ]

    # --- os estagios, na ordem, com o que cada um fez ---
    partes.append("ESTAGIOS")
    for nome, achados_ in resultado.estagios:
        n_erros = sum(1 for a in achados_ if a.severidade == ERRO)
        n_avisos = sum(1 for a in achados_ if a.severidade == AVISO)
        detalhe = f"{n_erros} erro(s), {n_avisos} aviso(s)"
        partes.append(f"  {nome:<10} {detalhe}")

    # Os estagios que nao rodaram tambem entram, marcados. Um relatorio que
    # so mostra o que rodou deixa o usuario sem saber se o resto foi
    # verificado ou se o pipeline simplesmente parou.
    rodados = {nome for nome, _ in resultado.estagios}
    for nome in ESTAGIOS:
        if nome in rodados:
            continue
        if nome == "testes" and not resultado.teste_pedido:
            # Distinguir "nao foi pedido" de "o anterior reprovou". Sem essa
            # distincao o relatorio diz que o pipeline parou num estagio que
            # passou, e quem le conclui que algo foi verificado e nao foi.
            partes.append(f"  {nome:<10} nao rodou (nao solicitado: use --origem e --destino)")
        else:
            partes.append(f"  {nome:<10} nao rodou (estagio anterior reprovou)")

    if resultado.interrompido_em:
        partes.extend(
            [
                "",
                f"INTERROMPIDO EM: {resultado.interrompido_em}",
                "Os estagios seguintes dependem deste e nao foram executados.",
                "Corrigir o achado acima e rodar de novo.",
            ]
        )

    # --- os achados, gravidade primeiro ---
    todos = resultado.achados
    if todos:
        partes.extend(["", "ACHADOS"])
        ordenados = sorted(
            todos, key=lambda a: (0 if a.severidade == ERRO else 1, a.linha, a.codigo)
        )
        for achado in ordenados:
            partes.append(_linha_regra(achado.codigo, achado.severidade))
            local = (
                f"linha {achado.linha}" if achado.linha else "arquivo inteiro"
            )
            partes.append(f"  onde: {local}")
            partes.append(f"  o que: {achado.mensagem}")
            if achado.sugestao:
                partes.append(f"  como corrigir: {achado.sugestao}")
            partes.append("")

    # --- o veredito ---
    partes.extend(
        [
            "=" * 72,
            f"RESULTADO: {resultado.status()}",
        ]
    )
    if resultado.passou:
        partes.append(
            "Todos os estagios rodaram. O candidato pode seguir para o merge."
        )
    elif resultado.bloqueia:
        partes.append(
            f"{resultado.contar(ERRO)} erro(s) bloqueiam o merge. "
            "O candidato nao pode ser aplicado."
        )
    else:
        partes.append(
            f"{resultado.contar(AVISO)} aviso(s). O candidato passa, "
            "mas o revisor precisa olhar."
        )

    return "\n".join(partes)


def salvar_json(resultado: Resultado, caminho: str | Path) -> Path:
    """Grava o resultado em JSON.

    Write the result as JSON.

    Args:
        resultado: O resultado do pipeline.
        caminho: O arquivo de destino.

    Returns:
        O caminho gravado.
    """
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(resultado.para_dict(), indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return caminho


def resumo_curto(resultado: Resultado) -> str:
    """Uma linha para o log do CI.

    One line for the CI log.

    Args:
        resultado: O resultado do pipeline.

    Returns:
        Uma linha com arquivo, status e contagens.
    """
    return (
        f"{resultado.arquivo}: {resultado.status()} - "
        f"{resultado.contar(ERRO)} erro(s), {resultado.contar(AVISO)} aviso(s)"
    )
