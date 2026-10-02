"""Parse de configuracao Cisco-like.

Parse Cisco-like configuration.

O parser e o unico modulo que sabe o que e uma linha de configuracao. Todo o
resto do pipeline - sintaxe, regras de negocio, golden config - consome a
estrutura que ele produz, e nao o texto. E por isso que ele separa
**comando** de **argumento**: uma regra de negocio que precisa do numero da
VLAN le um inteiro, nao a string `vlan 10`.

## O modelo

```mermaid
flowchart TD
    A[linha bruta] --> B{commentario?}
    B -->|sim| C[descartada]
    B -->|nao| D{vazia?}
    D -->|sim| C
    D -->|nao| E{tem dois pontos?}
    E -->|nao| F[Livre]
    E -->|sim| G[Estruturada]
    F --> H{esta dentro de interface?}
    H -->|sim| I[SubComando]
    H -->|nao| J[Comando]
    G --> K[chave, valor, filhos]
```

Uma `Interface` pode conter subcomandos, e um `Bloco` pode conter blocos
filhos. Isso reflecte o que o equipamento realmente faz: `interface Gi0/1`
agrupa `switchport mode access` e `switchport access vlan 10`, e nao ha
nenhum jeito de validar a VLAN sem saber sob qual interface ela foi
declarada.

## Por que o numero de linha vem junto

Toda peca guarda a linha de origem. Um relatorio que diz "VLAN 10 duplicada"
sem dizer onde estao as duas declaracoes e um relatorio que obriga o leitor a
abrir o arquivo e contar. E a pergunta mais comum depois de um CI vermelho e
"em que linha eu conserto isso".

A linha e 1-based, como todo editor mostra.

## O que o parser NAO faz

Nao valida. Um `switchport mode trun` sai do parser como comando de
primeiro nivel com argumento `trun`; o `sintaxe.py` e quem sabe que `trunk`
e a palavra. Separar as duas coisas e o que permite ter um unico parser e
varias camadas de validacao, em vez de um validador que cresce sem fim.

Nao conhece Cisco de verdade. O dialeto e plausivel, nao completo, e o
parser aceita o que o laboratorio precisa e recusa o que nao faz sentido
para ele.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Prefixo de comentario. Cisco usa `!`, e e o unico que o laboratorio usa.
COMENTARIO = "!"

# Prefixo de modo EXEC (comando de display, show, etc).
MODO_EXEC = " "

# Palavras que abrem um bloco de interface.
PALAVRAS_INTERFACE = ("interface",)

# Palavras que abrem um bloco de linhas de console. `line vty 0 4` agrupa o
# que vem depois, e sem reconhecer isso o `password` da linha seguinte vira
# um comando solto - o que faz o validador acusar "comando desconhecido" num
# arquivo perfeitamente correto.
PALAVRAS_LINHA = ("line",)

# Palavras que terminam um bloco.
PALAVRAS_SAIDA = ("exit", "end", "!")


class ErroDeParse(Exception):
    """O arquivo nao pode ser lido como configuracao.

    The file cannot be read as configuration.

    So e levantado para problema de arquivo - ilegivel, por exemplo. Comando
    desconhecido NAO e erro de parse: e entrada invalida, e quem reporta e o
    `sintaxe.py`.
    """


@dataclass
class Comando:
    """Uma linha de configuracao de primeiro nivel.

    A first-level configuration line.

    Attributes:
        nome: O comando, sem o prefixo de prompt.
        argumentos: A linha depois do comando, como veio.
        linha: Numero da linha no arquivo, 1-based.
    """

    nome: str
    argumentos: str
    linha: int

    def tokens(self) -> list[str]:
        """O comando dividido em partes.

        The command split into parts.

        Returns:
            Os argumentos separados por espaco.
        """
        return self.argumentos.split()

    def valor(self, indice: int = 0) -> str | None:
        """Um argumento pela posicao.

        One argument by position.

        Args:
            indice: A posicao, 0-based.

        Returns:
            O argumento, ou `None` se nao existe.
        """
        partes = self.tokens()
        if indice < len(partes):
            return partes[indice]
        return None

    def inteiro(self, indice: int = 0) -> int | None:
        """Um argumento convertido em inteiro.

        One argument converted to int.

        Args:
            indice: A posicao, 0-based.

        Returns:
            O inteiro, ou `None` se o argumento nao existe ou nao e numero.
        """
        bruto = self.valor(indice)
        if bruto is None:
            return None
        try:
            return int(bruto)
        except ValueError:
            return None


@dataclass
class SubComando(Comando):
    """Uma linha dentro de um bloco.

    A line inside a block.

    Herda de `Comando` de proposito: um subcomando tem nome, argumentos e
    linha, e trata-los como tipos diferentes obrigaria cada validador a
    duplicar a leitura dos dois.
    """


@dataclass
class Interface:
    """Um bloco `interface ...`.

    An `interface ...` block.

    Attributes:
        nome: O nome da interface, como declarado.
        subcomandos: As linhas dentro do bloco.
        linha: Numero da linha onde o bloco abre.
    """

    nome: str
    subcomandos: list[SubComando] = field(default_factory=list)
    linha: int = 0


@dataclass
class BlocoLinha:
    """Um bloco `line ...`, como `line vty 0 4`.

    A `line ...` block.

    Attributes:
        tipo: A palavra depois de `line`, como `vty` ou `console`.
        faixa: Os argumentos restantes, como `0 4`.
        subcomandos: As linhas dentro do bloco.
        linha: Numero da linha onde o bloco abre.
    """

    tipo: str
    faixa: str
    subcomandos: list[SubComando] = field(default_factory=list)
    linha: int = 0

    @property
    def nome(self) -> str:
        """O nome do bloco, como aparece no arquivo.

        The block's name, as it appears in the file.
        """
        return f"line {self.tipo} {self.faixa}".strip()


@dataclass
class Configuracao:
    """Um arquivo de configuracao inteiro, ja parseado.

    A whole configuration file, already parsed.

    Attributes:
        comandos: Os comandos de primeiro nivel, sem os de dentro de
            interface.
        interfaces: Os blocos de interface, na ordem de declaracao.
        caminho: O arquivo de origem, quando veio de disco.
    """

    comandos: list[Comando] = field(default_factory=list)
    interfaces: list[Interface] = field(default_factory=list)
    blocos_linha: list[BlocoLinha] = field(default_factory=list)
    caminho: str = ""

    def por_nome(self, nome: str) -> list[Comando]:
        """Todos os comandos com um dado nome.

        All commands with a given name.

        Args:
            nome: O nome do comando, sem argumentos.

        Returns:
            Os comandos, na ordem do arquivo. Vazio se nao houver.
        """
        return [c for c in self.comandos if c.nome == nome]

    def bloco_vty(self) -> BlocoLinha | None:
        """O primeiro bloco `line vty`, se houver.

        The first `line vty` block, if any.

        Returns:
            O bloco, ou `None` se o arquivo nao tiver acesso remoto.
        """
        for bloco in self.blocos_linha:
            if bloco.tipo == "vty":
                return bloco
        return None

    def interface(self, nome: str) -> Interface | None:
        """Ache uma interface pelo nome.

        Find an interface by name.

        Args:
            nome: O nome da interface.

        Returns:
            A interface, ou `None` se nao existir.
        """
        for interface in self.interfaces:
            if interface.nome == nome:
                return interface
        return None

    def dentro_de_interface(self, nome: str) -> list[SubComando]:
        """Os subcomandos de uma interface.

        The subcommands of an interface.

        Args:
            nome: O nome da interface.

        Returns:
            Os subcomandos, na ordem. Vazio se a interface nao existir.
        """
        interface = self.interface(nome)
        return list(interface.subcomandos) if interface else []

    def declaracoes_vlan(self) -> list[tuple[int, int, str | None]]:
        """As declaracoes de VLAN, com a linha de cada uma.

        The VLAN declarations, with the line of each.

        Returns:
            Tuplas ``(linha, id, nome)``, na ordem do arquivo.
        """
        achados: list[tuple[int, int, str | None]] = []
        for comando in self.comandos:
            if comando.nome != "vlan":
                continue
            identificador = comando.inteiro(0)
            if identificador is None:
                continue
            achados.append((comando.linha, identificador, comando.valor(1)))
        return achados

    def iter_todos(self) -> Iterator[Comando]:
        """Todos os comandos, incluindo os de dentro de interface.

        All commands, including those inside interfaces.

        Serve para quem precisa varrer tudo sem se preocupar com o nivel, como
        a busca por palavra proibida e a checagem de segredo.

        Yields:
            Cada comando, na ordem em que aparece no arquivo.
        """
        for comando in self.comandos:
            yield comando
        for interface in self.interfaces:
            for subcomando in interface.subcomandos:
                yield subcomando
        for bloco in self.blocos_linha:
            for subcomando in bloco.subcomandos:
                yield subcomando


def _limpa(linha: str) -> str:
    """Remove espacos das pontas.

    Strip leading and trailing spaces.

    Args:
        linha: A linha crua.

    Returns:
        A linha sem espacos nas pontas.
    """
    return linha.strip()


def parse_texto(texto: str, caminho: str = "") -> Configuracao:
    """Parse de um texto de configuracao.

    Parse a configuration text.

    Args:
        texto: O conteudo do arquivo.
        caminho: O nome do arquivo, para o relatorio citar a origem.

    Returns:
        A configuracao parseada.

    Raises:
        ErroDeParse: Se o texto nao puder ser dividido em linhas.
    """
    config = Configuracao(caminho=caminho)
    interface_atual: Interface | None = None
    bloco_atual: BlocoLinha | None = None

    for numero, bruta in enumerate(texto.splitlines(), start=1):
        # A indentacao e o sinal de bloco. E o unico sinal que nao depende de
        # vocabulario, e e o que o equipamento usa de verdade: um subcomando
        # esta indentado, um comando de primeiro nivel nao.
        #
        # A alternativa - exigir `exit` - obriga o arquivo a ter `exit` em
        # todo bloco, e configuracao real raramente tem. A outra alternativa
        # - fechar o bloco quando aparece outro bloco do mesmo tipo - so
        # resolve `interface`, e deixa `line vty` engolindo o resto do
        # arquivo. Nenhuma das duas e o comportamento do equipamento.
        indentado = bruta[:1].isspace()

        linha = _limpa(bruta)

        if not linha or linha.startswith(COMENTARIO):
            continue

        if linha in ("end", "exit"):
            interface_atual = None
            bloco_atual = None
            continue

        if not indentado:
            # Uma linha nao indentada fecha qualquer bloco aberto.
            interface_atual = None
            bloco_atual = None

        if interface_atual is not None:
            nome, argumentos = _divide(linha)
            interface_atual.subcomandos.append(
                SubComando(nome=nome, argumentos=argumentos, linha=numero)
            )
            continue

        if bloco_atual is not None:
            nome, argumentos = _divide(linha)
            bloco_atual.subcomandos.append(
                SubComando(nome=nome, argumentos=argumentos, linha=numero)
            )
            continue

        partes = linha.split(maxsplit=1)
        nome = partes[0]
        argumentos = partes[1] if len(partes) > 1 else ""

        if nome in PALAVRAS_INTERFACE:
            interface_atual = Interface(nome=argumentos.strip(), linha=numero)
            config.interfaces.append(interface_atual)
            continue

        if nome in PALAVRAS_LINHA:
            resto = argumentos.split(maxsplit=1)
            tipo = resto[0] if resto else ""
            faixa = resto[1] if len(resto) > 1 else ""
            bloco_atual = BlocoLinha(tipo=tipo, faixa=faixa, linha=numero)
            config.blocos_linha.append(bloco_atual)
            continue

        config.comandos.append(
            Comando(nome=nome, argumentos=argumentos, linha=numero)
        )

    return config


def _divide(linha: str) -> tuple[str, str]:
    """Separa o nome do comando dos argumentos.

    Split the command name from its arguments.

    Args:
        linha: A linha ja limpa.

    Returns:
        O par ``(nome, argumentos)``.
    """
    partes = linha.split(maxsplit=1)
    if len(partes) == 1:
        return partes[0], ""
    return partes[0], partes[1]


def parse_arquivo(caminho: str | Path) -> Configuracao:
    """Parse de um arquivo de configuracao.

    Parse a configuration file.

    Args:
        caminho: O arquivo.

    Returns:
        A configuracao parseada.

    Raises:
        ErroDeParse: Se o arquivo nao existir ou nao for UTF-8.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroDeParse(f"arquivo nao encontrado: {caminho}")

    try:
        texto = caminho.read_text(encoding="utf-8")
    except UnicodeDecodeError as erro:
        raise ErroDeParse(
            f"{caminho}: nao decodifica como UTF-8 ({erro.reason})"
        ) from None

    return parse_texto(texto, caminho=str(caminho))