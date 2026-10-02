"""Estagio 2: regras de negocio.

Stage 2: business rules.

O estagio que pergunta "faria sentido essa config no laboratorio?". A
sintaxe ja passou - aqui nao ha checagem de grafia: o alvo e a semantica.
Se a VLAN 10 foi declarada duas vezes, se a rota padrao aparece duas
vezes, se o proximo salto aponta para um endereco proprio, se a ACL
termina no `deny ip any any` ou deixa passar tudo que nao foi listado.

## As regras

Cada regra tem um `codigo` estavel, pelo mesmo motivo do estagio de
sintaxe: CI compara, e um codigo que muda de nome quebra o historico.

| codigo | severidade | o que e |
|---|---|---|
| `VLAN_DUPLICADA` | erro | mesma VLAN declarada duas vezes |
| `ROTA_PADRAO_DUPLICADA` | erro | mais de uma rota padrao |
| `ROTA_PARA_SI` | erro | proximo salto e endereco de interface do proprio arquivo |
| `ACL_SEM_DENY` | erro | ACL numerada que nao termina em `deny ip any any` |
| `SEM_FILTRO_DE_ENTRADA` | aviso | nenhum `access-list` no arquivo |
| `VLAN_SEM_INTERFACE` | aviso | VLAN declarada que nenhuma interface referencia |
| `SEM_MASCARA` | erro | `ip address` sem mascara |

`ACL_SEM_DENY` e o achado mais importante do estagio: o padrao implicito
de uma ACL e permitir, entao a lista sem o deny final deixa passar tudo
que nao foi listado.
"""

from __future__ import annotations

from dataclasses import dataclass

from .achado import AVISO, ERRO, Achado
from .parser import Comando, Configuracao

ESTAGIO = "regras"

# Rota padrao: a rede e a mascara que a identificam.
REDE_PADRAO = "0.0.0.0"
MASCARA_PADRAO = "255.255.255.0"


@dataclass(frozen=True)
class RegraNegocio:
    """Uma regra de negocio.

    A business rule.

    Subclasse de dataclass para deixar a lista legivel e para que o
    relatorio possa mostrar "N regras de negocio foram avaliadas".

    Attributes:
        codigo: Identificador estavel.
        descricao: O que a regra checa, em uma frase.
    """

    codigo: str
    descricao: str


REGRAS = (
    RegraNegocio("VLAN_DUPLICADA", "mesma VLAN declarada duas vezes"),
    RegraNegocio("ROTA_PADRAO_DUPLICADA", "mais de uma rota padrao para 0.0.0.0"),
    RegraNegocio(
        "ROTA_PARA_SI",
        "proximo salto da rota e endereco de interface do proprio arquivo",
    ),
    RegraNegocio("ACL_SEM_DENY", "ACL numerada que nao termina em 'deny ip any any'"),
    RegraNegocio("SEM_FILTRO_DE_ENTRADA", "nenhum access-list no arquivo"),
    RegraNegocio("VLAN_SEM_INTERFACE", "VLAN declarada que nenhuma interface referencia"),
    RegraNegocio("SEM_MASCARA", "ip address sem mascara"),
)


def _rotas(config: Configuracao) -> list[Comando]:
    """Os comandos `ip route` de primeiro nivel, na ordem do arquivo.

    The first-level `ip route` commands, in file order.

    Args:
        config: A configuracao parseada.

    Returns:
        Os comandos de rota, na ordem em que aparecem.
    """
    rotas: list[Comando] = []
    for comando in config.comandos:
        if comando.nome != "ip":
            continue
        tokens = comando.tokens()
        if tokens and tokens[0] == "route":
            rotas.append(comando)
    return rotas


def _ip_addresses(config: Configuracao) -> list[Comando]:
    """Todos os comandos `ip address`, na ordem em que aparecem.

    All `ip address` commands, in file order.

    Args:
        config: A configuracao parseada.

    Returns:
        Os comandos, na ordem do arquivo.
    """
    achados: list[Comando] = []
    for comando in config.iter_todos():
        if comando.nome != "ip":
            continue
        tokens = comando.tokens()
        if tokens and tokens[0] == "address":
            achados.append(comando)
    return achados


def _enderecos_de_interface(config: Configuracao) -> dict[str, int]:
    """Os enderecos declarados em `ip address`, com a linha de cada um.

    The addresses declared in `ip address`, with their lines.

    Args:
        config: A configuracao parseada.

    Returns:
        Mapeia endereco para a linha onde foi declarado.
    """
    enderecos: dict[str, int] = {}
    for comando in _ip_addresses(config):
        tokens = comando.tokens()
        if len(tokens) >= 2:
            enderecos.setdefault(tokens[1], comando.linha)
    return enderecos


def _checa_vlan_duplicada(config: Configuracao) -> list[Achado]:
    """VLAN declarada mais de uma vez.

    A VLAN declared more than once.

    Args:
        config: A configuracao parseada.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []
    vistas: dict[int, int] = {}

    for linha, identificador, _nome in config.declaracoes_vlan():
        if identificador in vistas:
            achados.append(
                Achado(
                    estagio=ESTAGIO,
                    severidade=ERRO,
                    codigo="VLAN_DUPLICADA",
                    mensagem=f"VLAN {identificador} declarada duas vezes",
                    linha=linha,
                    sugestao=f"a primeira declaracao esta na linha {vistas[identificador]}",
                )
            )
        else:
            vistas[identificador] = linha

    return achados


def _checa_rota_padrao(config: Configuracao) -> list[Achado]:
    """Mais de uma rota padrao.

    More than one default route.

    O equipamento obedece a ultima; a anterior fica escondida e ninguem
    sabe que ela existe.

    Args:
        config: A configuracao parseada.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []
    padroes = [
        rota
        for rota in _rotas(config)
        if len(rota.tokens()) >= 4
        and rota.tokens()[1] == REDE_PADRAO
        and rota.tokens()[2] == MASCARA_PADRAO
    ]

    for extra in padroes[1:]:
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="ROTA_PADRAO_DUPLICADA",
                mensagem=(
                    "rota padrao declarada mais de uma vez; "
                    "o equipamento obedece a ultima"
                ),
                linha=extra.linha,
                sugestao=(
                    f"a primeira declaracao esta na linha {padroes[0].linha}; "
                    "apague a que sobrar"
                ),
            )
        )

    return achados


def _checa_rota_para_si(config: Configuracao) -> list[Achado]:
    """Rota cujo proximo salto e endereco deste proprio arquivo.

    A route whose next hop is an address of this very file.

    Args:
        config: A configuracao parseada.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []
    enderecos = _enderecos_de_interface(config)

    for rota in _rotas(config):
        tokens = rota.tokens()
        if len(tokens) < 4:
            continue
        proximo = tokens[3]
        if proximo in enderecos:
            achados.append(
                Achado(
                    estagio=ESTAGIO,
                    severidade=ERRO,
                    codigo="ROTA_PARA_SI",
                    mensagem=(
                        f"proximo salto {proximo} e endereco de interface "
                        "desta configuracao"
                    ),
                    linha=rota.linha,
                    sugestao=(
                        f"o endereco e proprio deste arquivo "
                        f"(linha {enderecos[proximo]}); o pacote nunca sai"
                    ),
                )
            )

    return achados


def _checa_acl(config: Configuracao) -> list[Achado]:
    """ACL numerada que nao termina em `deny ip any any`.

    A numbered ACL that does not end in `deny ip any any`.

    O padrao implicito de uma ACL e permitir: a lista que nao termina no
    deny final deixa passar tudo que nao foi listado.

    Args:
        config: A configuracao parseada.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []
    ultimos: dict[int, Comando] = {}

    for comando in config.comandos:
        if comando.nome != "access-list":
            continue
        numero = comando.inteiro(0)
        if numero is None:
            continue
        ultimos[numero] = comando

    for numero, ultima in ultimos.items():
        tokens = ultima.tokens()
        if len(tokens) != 5 or tokens[1:5] != ["deny", "ip", "any", "any"]:
            achados.append(
                Achado(
                    estagio=ESTAGIO,
                    severidade=ERRO,
                    codigo="ACL_SEM_DENY",
                    mensagem=(
                        f"ACL {numero} nao termina em 'deny ip any any'; "
                        "o padrao implicito e permitir"
                    ),
                    linha=ultima.linha,
                    sugestao=(
                        f"adicione 'access-list {numero} deny ip any any' "
                        "como ultima entrada"
                    ),
                )
            )

    return achados


def _checa_filtro(config: Configuracao) -> list[Achado]:
    """Arquivo sem nenhum filtro de entrada.

    A file with no input filter.

    Args:
        config: A configuracao parseada.

    Returns:
        O aviso, ou lista vazia se existir `access-list`.
    """
    if config.por_nome("access-list"):
        return []
    return [
        Achado(
            estagio=ESTAGIO,
            severidade=AVISO,
            codigo="SEM_FILTRO_DE_ENTRADA",
            mensagem="nenhum access-list no arquivo; a entrada nao tem filtro",
            sugestao="crie uma ACL numerada para filtrar a entrada",
        )
    ]


def _ids_da_lista(texto: str) -> set[int]:
    """Um argumento de `trunk allowed vlan` em ids de VLAN.

    A `trunk allowed vlan` argument as VLAN ids.

    Aceita lista ("10,20,30") e faixa ("1-5").

    Args:
        texto: O argumento, como veio.

    Returns:
        O conjunto de ids aceitos.
    """
    ids: set[int] = set()
    for parte in texto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "-" in parte:
            extremos = parte.split("-")
            if (
                len(extremos) == 2
                and extremos[0].isdigit()
                and extremos[1].isdigit()
            ):
                ids.update(range(int(extremos[0]), int(extremos[1]) + 1))
        elif parte.isdigit():
            ids.add(int(parte))
    return ids


def _vlans_referenciadas(config: Configuracao) -> set[int]:
    """As VLANs que alguma interface referencia.

    The VLANs referenced by some interface.

    Conta tres formas: `switchport access vlan N`,
    `switchport trunk allowed vlan N,...` e a interface `VlanN`.

    Args:
        config: A configuracao parseada.

    Returns:
        O conjunto de identificadores.
    """
    referidas: set[int] = set()

    for interface in config.interfaces:
        nome = interface.nome
        if nome.upper().startswith("VLAN") and nome[4:].isdigit():
            referidas.add(int(nome[4:]))

    for comando in config.iter_todos():
        if comando.nome != "switchport":
            continue
        tokens = comando.tokens()
        if len(tokens) >= 3 and tokens[:2] == ["access", "vlan"]:
            identificador = comando.inteiro(2)
            if identificador is not None:
                referidas.add(identificador)
        elif len(tokens) >= 4 and tokens[:3] == ["trunk", "allowed", "vlan"]:
            referidas.update(_ids_da_lista(tokens[3]))

    return referidas


def _checa_vlan_sem_interface(config: Configuracao) -> list[Achado]:
    """VLAN declarada que nenhuma interface referencia.

    A declared VLAN no interface references.

    Args:
        config: A configuracao parseada.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []
    referidas = _vlans_referenciadas(config)
    vistas: set[int] = set()

    for linha, identificador, _nome in config.declaracoes_vlan():
        if identificador in vistas:
            continue  # a segunda declaracao ja e apontada como VLAN_DUPLICADA
        vistas.add(identificador)
        if identificador not in referidas:
            achados.append(
                Achado(
                    estagio=ESTAGIO,
                    severidade=AVISO,
                    codigo="VLAN_SEM_INTERFACE",
                    mensagem=f"VLAN {identificador} declarada mas nenhuma interface a referencia",
                    linha=linha,
                    sugestao="vincule a VLAN a uma interface ou remova a declaracao",
                )
            )

    return achados


def _checa_ip_address(config: Configuracao) -> list[Achado]:
    """`ip address` sem mascara.

    An `ip address` without mask.

    Args:
        config: A configuracao parseada.

    Returns:
        Os achados encontrados.
    """
    achados: list[Achado] = []

    for comando in _ip_addresses(config):
        tokens = comando.tokens()
        if len(tokens) < 3:
            achados.append(
                Achado(
                    estagio=ESTAGIO,
                    severidade=ERRO,
                    codigo="SEM_MASCARA",
                    mensagem=f"ip address sem mascara: '{' '.join(tokens[1:])}'",
                    linha=comando.linha,
                    sugestao="a forma e: ip address <endereco> <mascara>",
                )
            )

    return achados


def validar(config: Configuracao) -> list[Achado]:
    """Roda o estagio de regras de negocio.

    Run the business-rules stage.

    Args:
        config: A configuracao parseada.

    Returns:
        Os achados, em ordem de linha.
    """
    achados = (
        _checa_vlan_duplicada(config)
        + _checa_rota_padrao(config)
        + _checa_rota_para_si(config)
        + _checa_acl(config)
        + _checa_filtro(config)
        + _checa_vlan_sem_interface(config)
        + _checa_ip_address(config)
    )
    return sorted(achados, key=lambda a: (a.linha, a.codigo))


def tabela() -> list[RegraNegocio]:
    """As regras que este estagio avalia.

    The rules this stage evaluates.

    Returns:
        A lista de regras, com codigo e descricao.
    """
    return list(REGRAS)
