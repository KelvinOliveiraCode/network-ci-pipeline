"""Estagio 3: comparacao com a golden config.

Stage 3: comparison against the golden config.

O estagio que pergunta "esta config continua estruturalmente completa?".
Ele compara o candidato contra a configuracao de referencia - o estado
conhecido como bom do equipamento - e decide se o que muda e mudanca ou
perda.

A regra de ouro deste estagio: golden config NAO e igualdade estrita. Se
fosse, toda mudanca legitima seria reprovada - uma VLAN nova, uma
interface a mais, uma a menos - e o time aprenderia a ignorar o CI, que
e o que o estagio esta tentando impedir.

Entao a comparacao e sobre o que e estrutural, nao sobre a lista
completa. O estagio confere a presenca do que nao pode faltar em
nenhuma config saudavel: o acesso administrativo (enable secret e line
vty com password), o filtro de entrada (ACL numerada terminando em
deny), o spanning-tree e um uplink em trunk.

E o que falta do golden - uma VLAN opcional, uma interface a menos -
NAO e achado. Faltou configuracao opcional, o estagio nao e dono dessa
decisao; quem decide e o revisor, com o plano na mao.

## As regras

Cada regra tem um `codigo` estavel, como nos demais estagios: CI
precisa comparar, e um achado que muda de nome a cada versao apaga o
historico.

| codigo | severidade | o que e |
|---|---|---|
| `SEM_ENABLE_SECRET` | erro | candidato sem `enable secret` |
| `SEM_LINE_VTY` | erro | candidato sem bloco `line vty` |
| `VTY_SEM_PASSWORD` | erro | `line vty` sem `password` em nenhuma das linhas |
| `ACL_SEM_DENY_ANY` | erro | ACL numerada que nao termina em `deny ip any any` |
| `SEM_SPANNING_TREE` | erro | candidato sem `spanning-tree mode` |
| `SEM_INTERFACE_TRUNK` | erro | nenhuma interface em modo trunk |
| `VLAN_NOVA` | aviso | VLAN no candidato que a referencia nao declara |

`VLAN_NOVA` e aviso e nao erro de proposito: uma VLAN nova e mudanca
legitima, e bloquear por ela treinaria o time a apagar a linha do
relatorio. O revisor precisa saber que ela existe; e por isso que ela
aparece.
"""

from __future__ import annotations

from dataclasses import dataclass

from .achado import AVISO, ERRO, Achado
from .parser import BlocoLinha, Comando, Configuracao

ESTAGIO = "golden"

# Faixa de ACL numerada estandard, a mesma que o estagio de sintaxe usa.
ACL_MIN = 1
ACL_MAX = 199

# A ultima entrada de uma ACL numerada precisa ser exatamente essa.
DENY_ANY = ("deny", "ip", "any", "any")

# Subcomandos que podem aparecer dentro de um bloco `line vty`. O parser
# nao abre bloco para `line`, entao "dentro do bloco" e definido aqui: os
# comandos seguintes ate o primeiro que nao e subcomando de linha.
SUBCOMANDOS_LINHA = (
    "password",
    "transport",
    "login",
    "exec-timeout",
    "access-class",
)


@dataclass(frozen=True)
class RegraGolden:
    """Uma regra de golden config.

    A golden-config rule.

    Subclasse de dataclass para deixar a lista legivel e para que o
    relatorio possa mostrar "N regras de golden foram avaliadas".

    Attributes:
        codigo: Identificador estavel.
        descricao: O que a regra checa, em uma frase.
    """

    codigo: str
    descricao: str


REGRAS_GOLDEN = (
    RegraGolden("SEM_ENABLE_SECRET", "candidato sem enable secret"),
    RegraGolden("SEM_LINE_VTY", "candidato sem bloco line vty"),
    RegraGolden("VTY_SEM_PASSWORD", "line vty sem password em nenhuma das linhas"),
    RegraGolden(
        "ACL_SEM_DENY_ANY",
        "ACL numerada que nao termina em deny ip any any",
    ),
    RegraGolden("SEM_SPANNING_TREE", "candidato sem spanning-tree mode"),
    RegraGolden("SEM_INTERFACE_TRUNK", "nenhuma interface em modo trunk"),
    RegraGolden("VLAN_NOVA", "VLAN no candidato que a referencia nao declara"),
)


def _tem_enable_secret(config: Configuracao) -> bool:
    """Se ha `enable secret` no arquivo.

    Whether the file has an `enable secret`.
    """
    for comando in config.comandos:
        if comando.nome == "enable" and comando.valor(0) == "secret":
            return True
    return False


def _blocos_vty(config: Configuracao) -> list[BlocoLinha]:
    """Os blocos `line vty`, na ordem do arquivo.

    The `line vty` blocks, in file order.

    O parser abre bloco para `line`, entao o acesso remoto vive em
    `config.blocos_linha` e nao em `config.comandos`. A versao anterior deste
    modulo varria `comandos` procurando `line vty` e inferia onde o bloco
    acabava pelo primeiro comando seguinte que nao era subcomando de linha -
    um remendo para o parser nao abrir bloco. O parser agora abre, e a
    inferencia foi embora.
    """
    return [bloco for bloco in config.blocos_linha if bloco.tipo == "vty"]


def _tem_password_em_vty(bloco: BlocoLinha, config: Configuracao) -> bool:
    """Se o bloco `line vty` tem `password` entre as linhas internas.

    Whether the `line vty` block has a `password` on any of its lines.
    """
    return any(subcomando.nome == "password" for subcomando in bloco.subcomandos)


def _acls_numericas(config: Configuracao) -> dict[int, list[Comando]]:
    """As ACLs numeradas, por numero, na ordem do arquivo.

    The numbered ACLs, keyed by number, in file order.
    """
    acls: dict[int, list[Comando]] = {}
    for comando in config.comandos:
        if comando.nome != "access-list":
            continue
        numero = comando.inteiro(0)
        if numero is None or not ACL_MIN <= numero <= ACL_MAX:
            continue
        acls.setdefault(numero, []).append(comando)
    return acls


def _tem_spanning_tree(config: Configuracao) -> bool:
    """Se ha `spanning-tree mode` no arquivo.

    Whether the file has a `spanning-tree mode`.
    """
    for comando in config.comandos:
        if comando.nome == "spanning-tree" and comando.valor(0) == "mode":
            return True
    return False


def _tem_interface_trunk(config: Configuracao) -> bool:
    """Se alguma interface esta em modo trunk.

    Whether any interface is in trunk mode.
    """
    for interface in config.interfaces:
        for subcomando in interface.subcomandos:
            if subcomando.nome == "switchport" and subcomando.tokens()[:2] == [
                "mode",
                "trunk",
            ]:
                return True
    return False


def _vlans_novas(
    candidato: Configuracao, referencia: Configuracao
) -> list[tuple[int, int]]:
    """As VLANs do candidato que a referencia nao declara.

    The candidate's VLANs that the reference does not declare.

    VLAN que existe so no golden NAO entra aqui: falta de
    configuracao opcional e decisao do revisor, nao achado deste
    estagio.

    Returns:
        Pares ``(linha, id)``, na ordem do arquivo do candidato.
    """
    conhecidas = {
        identificador for _, identificador, _ in referencia.declaracoes_vlan()
    }
    return [
        (linha, identificador)
        for linha, identificador, _ in candidato.declaracoes_vlan()
        if identificador not in conhecidas
    ]


def _checa_acesso(config: Configuracao) -> list[Achado]:
    """As regras de acesso administrativo.

    The administrative-access rules.
    """
    achados: list[Achado] = []

    if not _tem_enable_secret(config):
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="SEM_ENABLE_SECRET",
                mensagem="configuracao sem enable secret",
                sugestao=(
                    "sem isso nao ha modo privilegiado; o equipamento fica "
                    "administravel so por console fisico"
                ),
            )
        )

    vty = _blocos_vty(config)
    if not vty:
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="SEM_LINE_VTY",
                mensagem="configuracao sem bloco line vty",
                sugestao="sem line vty nao ha acesso remoto ao equipamento",
            )
        )
    else:
        for bloco in vty:
            if not _tem_password_em_vty(bloco, config):
                achados.append(
                    Achado(
                        estagio=ESTAGIO,
                        severidade=ERRO,
                        codigo="VTY_SEM_PASSWORD",
                        mensagem=(
                            f"bloco {bloco.nome} sem password "
                            "em nenhuma das linhas"
                        ),
                        linha=bloco.linha,
                        sugestao="adicionar 'password' dentro do bloco line vty",
                    )
                )

    return achados


def _checa_acl(config: Configuracao) -> list[Achado]:
    """A regra do filtro de entrada.

    The input-filter rule.
    """
    achados: list[Achado] = []
    acls = _acls_numericas(config)
    for numero in sorted(acls):
        ultima = acls[numero][-1]
        # O numero da ACL e o primeiro token dos argumentos; o corpo da
        # entrada e o que vem depois.
        if ultima.tokens()[1:] != list(DENY_ANY):
            achados.append(
                Achado(
                    estagio=ESTAGIO,
                    severidade=ERRO,
                    codigo="ACL_SEM_DENY_ANY",
                    mensagem=f"ACL {numero} nao termina em 'deny ip any any'",
                    linha=ultima.linha,
                    sugestao=(
                        "a ultima entrada de uma ACL numerada precisa ser "
                        "deny ip any any"
                    ),
                )
            )
    return achados


def _checa_rede(config: Configuracao) -> list[Achado]:
    """As regras de alcance: spanning-tree e uplink em trunk.

    The reachability rules: spanning-tree and a trunk uplink.
    """
    achados: list[Achado] = []

    if not _tem_spanning_tree(config):
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="SEM_SPANNING_TREE",
                mensagem="configuracao sem spanning-tree mode",
                sugestao="definir o modo spanning-tree do switch",
            )
        )

    if not _tem_interface_trunk(config):
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="SEM_INTERFACE_TRUNK",
                mensagem="nenhuma interface em modo trunk",
                sugestao=(
                    "um switch de acesso sem uplink nao se conecta ao resto; "
                    "colocar uma porta em trunk"
                ),
            )
        )

    return achados


def _checa_vlans_novas(
    candidato: Configuracao, referencia: Configuracao
) -> list[Achado]:
    """A regra do que o candidato declara a mais que a referencia.

    The rule for what the candidate declares beyond the reference.
    """
    achados: list[Achado] = []
    for linha, identificador in _vlans_novas(candidato, referencia):
        achados.append(
            Achado(
                estagio=ESTAGIO,
                severidade=AVISO,
                codigo="VLAN_NOVA",
                mensagem=(
                    f"VLAN {identificador} declarada no candidato "
                    "mas ausente na referencia"
                ),
                linha=linha,
                sugestao=(
                    "VLAN nova nao bloqueia; o revisor precisa saber "
                    "que ela existe"
                ),
            )
        )
    return achados


def comparar(
    candidato: Configuracao, referencia: Configuracao
) -> list[Achado]:
    """Compara o candidato contra a golden config.

    Compare the candidate against the golden config.

    A comparacao e sobre o que e estrutural, nunca igualdade estrita:
    confere a presenca do que nao pode faltar em nenhuma config
    saudavel e ignora o que so existe na referencia.

    Args:
        candidato: A configuracao parseada sob avaliacao.
        referencia: A configuracao de referencia (golden).

    Returns:
        Os achados, em ordem de linha.
    """
    achados = (
        _checa_acesso(candidato)
        + _checa_acl(candidato)
        + _checa_rede(candidato)
        + _checa_vlans_novas(candidato, referencia)
    )
    return sorted(achados, key=lambda achado: (achado.linha, achado.codigo))


def tabela() -> list[RegraGolden]:
    """As regras que este estagio avalia.

    The rules this stage evaluates.

    Returns:
        A lista de regras, com codigo e descricao.
    """
    return list(REGRAS_GOLDEN)
