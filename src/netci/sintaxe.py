"""Estagio 1: validacao sintatica.

Stage 1: syntax validation.

O estagio que pergunta "esta config faz sentido como texto?". Ele nao sabe se
a VLAN 10 pode existir, se a ACL precisa existir, se o resultado e o
esperado. Sabe se `switchport mode trun` e uma palavra valida, se um
argumento numerico virou numero, se um bloco de interface foi fechado.

A separacao importa para o relatorio: um erro de sintaxe e uma coisa
completamente diferente de um erro de negocio, e quem le o relatorio precisa
saber qual dos dois aconteceu antes de ir abrir o arquivo.

## As regras

Cada regra tem um `codigo` estavel. Codigo estavel porque CI precisa
comparar: um alerta que muda de nome a cada versao faz o historico do
pipeline deixar de fazer sentido, e ninguem aprende a ler o que muda.

| codigo | severidade | o que e |
|---|---|---|
| `COMANDO_DESCONHECIDO` | erro | primeira palavra fora do vocabulario |
| `PARAMETRO_INVALIDO` | erro | argumento que deveria ser numero nao e |
| `VALOR_INVALIDO` | erro | valor fora do conjunto permitido |
| `INTERFACE_DUPLICADA` | erro | mesma interface declarada duas vezes |
| `INTERFACE_VAZIA` | aviso | bloco `interface` sem nenhum subcomando |
| `SUBCOMANDO_DESCONHECIDO` | aviso | linha dentro de interface nao reconhecida |
| `SEM_HOSTNAME` | aviso | arquivo sem `hostname`, que complica o log do equipamento |

`SUBCOMANDO_DESCONHECIDO` e aviso e nao erro de proposito: o vocabulario
conhecido cresce a cada equipamento novo do laboratorio, e bloquear o merge
por uma linha nova e legitima seria treinar o time a ignorar o estagio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .achado import AVISO, ERRO, Achado
from .parser import Comando, Configuracao

ESTAGIO = "sintaxe"

# Vocabulario de primeiro nivel do laboratorio. Uma palavra fora daqui vira
# achado, e o achado carrega a palavra - quem le ja sabe o que corrigir sem
# abrir o arquivo.
VOCABULARIO: dict[str, str] = {
    "hostname": "texto",
    "vlan": "vlan",
    "interface": "interface",
    "ip": "ip",
    "ip route": "rota",
    "access-list": "acl",
    "line": "line",
    "spanning-tree": "stp",
    "aaa": "aaa",
    "username": "texto",
    "enable": "texto",
    "description": "texto",
    # `name` aparece logo depois de um `vlan N` e da nome a ela. Sem ele no
    # vocabulario, um arquivo que nomeia as VLANs - que e o normal - seria
    # reprovado por "comando desconhecido".
    "name": "texto",
    "no": "negativo",
    "exit": "nenhum",
    "end": "nenhum",
}

# Subcomandos conhecidos dentro de interface. Fora daqui, aviso.
VOCABULARIO_INTERFACE: dict[str, str] = {
    "switchport": "switchport",
    "no shutdown": "shutdown",
    "shutdown": "shutdown",
    "ip address": "ip",
    "description": "texto",
    "speed": "texto",
    "duplex": "texto",
    "channel-group": "grupo",
}

# Subcomandos conhecidos dentro de `line vty`. Sem esta lista, o `password` e
# o `transport input` de um bloco de acesso remoto seriam "comando
# desconhecido", e um arquivo de configuracao perfeito seria reprovado no
# primeiro estagio por causa do parser.
VOCABULARIO_LINHA: dict[str, str] = {
    "password": "texto",
    "transport": "transport",
    "login": "login",
    "exec": "texto",
    "session-limit": "numero",
}

# Valores aceitos em `switchport mode`.
MODOS_PORTA = {"access", "trunk", "dynamic", "dot1q-tunnel"}

# Faixa de VLAN valida. 0 e 4095 sao reservados e nao aparecem em declaracao.
VLAN_MIN = 1
VLAN_MAX = 4094


@dataclass(frozen=True)
class RegraSintaxe:
    """Uma regra de sintaxe.

    A syntax rule.

    Subclasse de dataclass para deixar a lista legivel e para que o
    relatorio possa mostrar "N regras sintaticas foram avaliadas".

    Attributes:
        codigo: Identificador estavel.
        descricao: O que a regra checa, em uma frase.
    """

    codigo: str
    descricao: str


REGRAS_SINTATIXE = (
    RegraSintaxe("COMANDO_DESCONHECIDO", "primeira palavra fora do vocabulario"),
    RegraSintaxe("PARAMETRO_INVALIDO", "argumento numerico que nao e numero"),
    RegraSintaxe("VALOR_INVALIDO", "valor fora do conjunto permitido"),
    RegraSintaxe("INTERFACE_DUPLICADA", "mesma interface declarada duas vezes"),
    RegraSintaxe("INTERFACE_VAZIA", "bloco interface sem subcomando"),
    RegraSintaxe("SUBCOMANDO_DESCONHECIDO", "linha de interface nao reconhecida"),
    RegraSintaxe("SEM_HOSTNAME", "arquivo sem comando hostname"),
)


def _primeira_palavra(comando: Comando) -> str:
    """A palavra que decide se o comando existe.

    The word that decides whether the command exists.

    `ip route` e `access-list` tem a parte descritiva fora do nome. Sem isso,
    `ip` sozinho - que so aparece com `ip address` - seria vocabulario de
    primeiro nivel e aceitaria `ip qualquer-coisa`.

    Args:
        comando: O comando.

    Returns:
        A palavra de duas partes se o comando comecar por uma, ou o nome.
    """
    if comando.nome in ("ip", "no") and comando.tokens():
        return f"{comando.nome} {comando.tokens()[0]}"
    return comando.nome


def _checa_comando(config: Configuracao) -> list[Achado]:
    """As regras que valem para comandos de primeiro nivel.

    The rules that apply to first-level commands.

    Args:
        config: A configuracao parseada.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []

    for comando in config.comandos:
        palavra = _primeira_palavra(comando)

        # `no shutdown` e um subcomando de interface, nao comando solto. Se
        # aparecer fora de interface, e config invalida.
        tipo = VOCABULARIO.get(palavra)
        if tipo is None:
            # A mensagem cita a palavra que falhou, e nao `comando.nome`. Para
            # `ip banana` o nome e `ip`, que existe: dizer "comando
            # desconhecido: ip" manda o leitor procurar um comando valido que
            # ele acabou de escrever corretamente.
            achados.append(
                Achado(
                    estagio=ESTAGIO,
                    severidade=ERRO,
                    codigo="COMANDO_DESCONHECIDO",
                    mensagem=f"comando desconhecido: {palavra}",
                    linha=comando.linha,
                    sugestao=f"verifique a grafia de '{palavra}'",
                )
            )
            continue

        if tipo == "vlan":
            achados.extend(_checa_vlan(comando))

        if tipo == "acl":
            achados.extend(_checa_acl(comando))

        if tipo == "rota":
            achados.extend(_checa_rota(comando))

    if not config.por_nome("hostname"):
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=AVISO,
                codigo="SEM_HOSTNAME",
                mensagem="configuracao sem comando hostname",
                sugestao="o equipamento mostra o IP padrao no log, e nao o nome",
            )
        )

    return achados


def _checa_vlan(comando: Comando) -> list[Achado]:
    """A sintaxe de uma declaracao de VLAN.

    A declaration's syntax.

    Args:
        comando: O comando `vlan`.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []
    identificador = comando.inteiro(0)

    if identificador is None:
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="PARAMETRO_INVALIDO",
                mensagem=f"id de VLAN invalido: '{comando.valor(0)}'",
                linha=comando.linha,
                sugestao="o id precisa ser um numero, de 1 a 4094",
            )
        )
        return achados

    if not VLAN_MIN <= identificador <= VLAN_MAX:
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="VALOR_INVALIDO",
                mensagem=f"VLAN {identificador} fora de {VLAN_MIN}..{VLAN_MAX}",
                linha=comando.linha,
                sugestao="0 e 4095 sao reservados e nao aceitam uso",
            )
        )

    return achados


def _checa_acl(comando: Comando) -> list[Achado]:
    """A sintaxe de uma ACL.

    An ACL's syntax.

    Args:
        comando: O comando `access-list`.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []
    numero = comando.inteiro(0)

    if numero is None:
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="PARAMETRO_INVALIDO",
                mensagem=f"numero de ACL invalido: '{comando.valor(0)}'",
                linha=comando.linha,
            )
        )
        return achados

    # ACL numerada padrao comeca em 1. As extendidas vao de 1300 para cima;
    # o laboratorio so valida a faixa estandard.
    # mas o laboratorio so valida a faixa que ele usa.
    if not 1 <= numero <= 199:
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=AVISO,
                codigo="VALOR_INVALIDO",
                mensagem=f"ACL {numero} fora da faixa estandard 1..199",
                linha=comando.linha,
            )
        )

    return achados


def _checa_rota(comando: Comando) -> list[Achado]:
    """A sintaxe de uma rota.

    A route's syntax.

    O comando chega como `nome="ip"` e `argumentos="route 0.0.0.0
    255.255.255.0 192.168.20.1"`. A palavra `route` e a posicao 0 dos
    argumentos, entao rede, mascara e proximo salto comecam em 1 - nao em 0.
    Pegar a posicao errada aqui faz `route` ser validado como endereco, e o
    arquivo inteiro ser reprovado no estagio de sintaxe em vez do de regras.

    Args:
        comando: O comando `ip route`.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []
    partes = comando.tokens()

    if partes[:1] != ["route"]:
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="VALOR_INVALIDO",
                mensagem=f"subcomando de ip desconhecido: {partes[0] if partes else '?'}",
                linha=comando.linha,
            )
        )
        return achados

    if len(partes) < 4:
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="PARAMETRO_INVALIDO",
                mensagem="rota sem destino e proximo salto",
                linha=comando.linha,
                sugestao="a forma e: ip route <rede> <mascara> <proximo>",
            )
        )
        return achados

    for indice in (1, 2):
        if not _parece_rede(partes[indice]):
            achados.append(
                Achado(
                    estagio=ESTAGIO,
                    severidade=ERRO,
                    codigo="PARAMETRO_INVALIDO",
                    mensagem=f"endereco de rota invalido: '{partes[indice]}'",
                    linha=comando.linha,
                )
            )

    return achados


_PADRAO_IP = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def _parece_rede(texto: str) -> bool:
    """Se o texto parece um endereco IPv4.

    Whether the text looks like an IPv4 address.

    Deliberadamente frouxo: a forma e o que se checa no estagio de sintaxe. Se
    cada octeto fosse validado aqui, `999.1.1.1` passaria por sintaxe e
    falharia so na regra de negocio, e o relatorio apontaria o estagio
    errado.

    Args:
        texto: O candidato.

    Returns:
        Verdadeiro se casa com a forma de um IPv4.
    """
    return bool(_PADRAO_IP.match(texto))


def _checa_interfaces(config: Configuracao) -> list[Achado]:
    """As regras que valem para blocos de interface.

    The rules that apply to interface blocks.

    Args:
        config: A configuracao parseada.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []
    vistas: dict[str, int] = {}

    for interface in config.interfaces:
        if interface.nome in vistas:
            achados.append(
                Achado(
                    estagio=ESTAGIO,
                    severidade=ERRO,
                    codigo="INTERFACE_DUPLICADA",
                    mensagem=f"interface {interface.nome} declarada duas vezes",
                    linha=interface.linha,
                    sugestao=f"a primeira declaracao esta na linha {vistas[interface.nome]}",
                )
            )
        else:
            vistas[interface.nome] = interface.linha

        if not interface.subcomandos:
            achados.append(
                Achado(
                    estagio=ESTAGIO,
                    severidade=AVISO,
                    codigo="INTERFACE_VAZIA",
                    mensagem=f"interface {interface.nome} sem nenhum comando",
                    linha=interface.linha,
                    sugestao="um bloco vazio nao configura nada",
                )
            )
            continue

        achados.extend(_checa_subcomandos(interface))

    achados.extend(_checa_blocos_linha(config))

    return achados


def _checa_blocos_linha(config: Configuracao) -> list[Achado]:
    """As regras que valem para blocos `line vty`.

    The rules that apply to `line vty` blocks.

    Args:
        config: A configuracao parseada.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []

    for bloco in config.blocos_linha:
        if not bloco.subcomandos:
            achados.append(
                Achado(
                    estagio=ESTAGIO,
                    severidade=AVISO,
                    codigo="BLOCO_LINHA_VAZIO",
                    mensagem=f"bloco {bloco.nome} sem nenhum comando",
                    linha=bloco.linha,
                )
            )
            continue

        for subcomando in bloco.subcomandos:
            if subcomando.nome not in VOCABULARIO_LINHA:
                achados.append(
                    Achado(
                        estagio=ESTAGIO,
                        severidade=AVISO,
                        codigo="SUBCOMANDO_DESCONHECIDO",
                        mensagem=(
                            f"linha nao reconhecida em {bloco.nome}: {subcomando.nome}"
                        ),
                        linha=subcomando.linha,
                    )
                )

    return achados


def _checa_subcomandos(interface) -> list[Achado]:
    """Os subcomandos de uma interface.

    One interface's subcommands.

    Args:
        interface: A interface a conferir.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []

    for subcomando in interface.subcomandos:
        palavra = _primeira_palavra(subcomando)
        if palavra not in VOCABULARIO_INTERFACE and subcomando.nome not in (
            "switchport", "no", "shutdown", "ip", "description",
            "speed", "duplex", "channel-group",
        ):
            achados.append(
                Achado(
                    estagio=ESTAGIO,
                    severidade=AVISO,
                    codigo="SUBCOMANDO_DESCONHECIDO",
                    mensagem=(
                        f"linha nao reconhecida em {interface.nome}: {subcomando.nome}"
                    ),
                    linha=subcomando.linha,
                    sugestao="pode ser comando novo do laboratorio; confira a lista",
                )
            )
            continue

        achados.extend(_checa_switchport(interface, subcomando))

    return achados


def _checa_switchport(interface, subcomando: Comando) -> list[Achado]:
    """A sintaxe de `switchport mode` e `switchport access vlan`.

    The syntax of `switchport mode` and `switchport access vlan`.

    Args:
        interface: A interface dona da linha.
        subcomando: O subcomando a conferir.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []
    partes = subcomando.tokens()

    if partes[:1] != ["mode"]:
        if partes[:2] == ["access", "vlan"]:
            identificador = subcomando.inteiro(2)
            if identificador is None:
                achados.append(
                    Achado(
                        estagio=ESTAGIO,
                        severidade=ERRO,
                        codigo="PARAMETRO_INVALIDO",
                        mensagem=f"VLAN de acesso invalida: '{subcomando.valor(2)}'",
                        linha=subcomando.linha,
                    )
                )
            elif not VLAN_MIN <= identificador <= VLAN_MAX:
                achados.append(
                    Achado(
                        estagio=ESTAGIO,
                        severidade=ERRO,
                        codigo="VALOR_INVALIDO",
                        mensagem=f"VLAN {identificador} fora de {VLAN_MIN}..{VLAN_MAX}",
                        linha=subcomando.linha,
                    )
                )
        return achados

    modo = partes[1] if len(partes) > 1 else None
    if modo is None:
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="PARAMETRO_INVALIDO",
                mensagem="switchport mode sem valor",
                linha=subcomando.linha,
            )
        )
    elif modo not in MODOS_PORTA:
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="VALOR_INVALIDO",
                mensagem=(
                    f"modo de porta invalido: '{modo}'; "
                    f"aceitos: {', '.join(sorted(MODOS_PORTA))}"
                ),
                linha=subcomando.linha,
                sugestao=f"em {interface.nome}, 'trun' quase sempre quer dizer 'trunk'",
            )
        )

    return achados


def validar(config: Configuracao) -> list[Achado]:
    """Roda o estagio de sintaxe.

    Run the syntax stage.

    Args:
        config: A configuracao parseada.

    Returns:
        Os achados, em ordem de linha.
    """
    achados = _checa_comando(config) + _checa_interfaces(config)
    return sorted(achados, key=lambda a: (a.linha, a.codigo))


def tabela() -> list[RegraSintaxe]:
    """As regras que este estagio avalia.

    The rules this stage evaluates.

    Returns:
        A lista de regras, com codigo e descricao.
    """
    return list(REGRAS_SINTATIXE)