"""O pipeline local de CI de rede.

The local network CI pipeline.

Cinco estagios em ordem: **sintaxe, regras de negocio, golden config, teste
simulado, relatorio**. Cada um recebe a saida do anterior, e o pipeline para
no primeiro que falha.

Parar no primeiro e uma escolha, e a alternativa seria rodar tudo e juntar os
erros. A alternativa parece mais util - a pessoa ve os cinco problemas de uma
vez - e na verdade e pior: um erro de sintaxe muda a leitura de todas as
regras de negocio depois, entao os erros de regra viram consequencia do de
sintaxe e nao causa. Quem le um relatorio com sete erros, dos quais seis sao
consequencia de um, corrige o primeiro, roda de novo, e so entao ve os
outros.

A excecao e o relatorio, que sempre roda: e ele que diz o que aconteceu.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]