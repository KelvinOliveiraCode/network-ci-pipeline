"""O tipo de achado, compartilhado por todos os estagios.

The finding type, shared by every stage.

Todos os estagios produzem a mesma coisa: uma lista de `Achado`. O `sintaxe`
acha linha malformada, as regras de negocio acham VLAN duplicada, o golden
acha linha a mais, o teste simulado acha caminho fechado. Sao coisas
diferentes com a mesma forma, e essa forma e o que permite:

- o relatorio nao conhecer nenhum estagio;
- a CLI imprimir qualquer achado sem switch por tipo;
- um teste de relatorio funcionar com achados inventados, sem rodar pipeline.

## Severidade

Dois niveis, e a distincao e sobre quem age:

- **`erro`** bloqueia o merge. A config esta errada.
- **`aviso`** nao bloqueia. E um desvio que o revisor precisa ver e decidir.

Um pipeline que bloqueia por tudo treina o time a ignorar o vermelho, e um
pipeline que nunca bloqueia nao e CI. A separacao e o que mantem os dois
sendo levados a serio - e por isso que a regra de cada estagio declara a
severidade, em vez de o relatorio inventar uma no final.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

ERRO = "erro"
AVISO = "aviso"


@dataclass(frozen=True)
class Achado:
    """Uma coisa errada em uma configuracao, com onde ela esta.

    One wrong thing in a configuration, with its location.

    Attributes:
        estagio: Qual estagio achou.
        severidade: `ERRO` ou `AVISO`.
        codigo: Identificador estavel da regra, como `VLAN_DUPLICADA`.
        mensagem: O que aconteceu, em uma frase.
        linha: Numero da linha no arquivo, ou 0 se for do arquivo inteiro.
        sugestao: O que fazer, quando houver uma resposta obvia.
    """

    estagio: str
    severidade: str
    codigo: str
    mensagem: str
    linha: int = 0
    sugestao: str = ""

    @property
    def bloqueia(self) -> bool:
        """Se o achado impede o merge.

        Whether the finding blocks the merge.
        """
        return self.severidade == ERRO

    def resumo(self) -> str:
        """O achado em uma linha, com a posicao.

        The finding on one line, with its location.

        Returns:
            ``arquivo:linha: [estagio] codigo - mensagem``.
        """
        posicao = f"linha {self.linha}" if self.linha else "arquivo inteiro"
        return f"{posicao}: [{self.estagio}] {self.codigo} - {self.mensagem}"


def erros(achados: Iterable[Achado]) -> list[Achado]:
    """So os achados que bloqueiam.

    Only the findings that block.

    Args:
        achados: Os achados.

    Returns:
        Os que tem severidade `ERRO`.
    """
    return [a for a in achados if a.bloqueia]


def avisos(achados: Iterable[Achado]) -> list[Achado]:
    """So os achados que nao bloqueiam.

    Only the findings that do not block.

    Args:
        achados: Os achados.

    Returns:
        Os que tem severidade `AVISO`.
    """
    return [a for a in achados if not a.bloqueia]