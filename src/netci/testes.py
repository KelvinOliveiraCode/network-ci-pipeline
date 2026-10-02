"""Estagio 4: teste de conectividade simulado.

Stage 4: simulated connectivity test.

O unico estagio que responde a pergunta "esse caminho existe?", e a resposta
e sobre **logica de enderecamento**, nao sobre a rede. Nada aqui abre socket,
resolve nome ou fala com equipamento. O modulo inteiro e aritmetica de
endereco.

## As tres saidas

O estagio tem exatamente tres resultados possiveis, e os tres precisam estar
corretos:

| codigo | quando |
|---|---|
| `TESTE_OK` | o caminho existe e nenhuma ACL nega |
| `TESTE_SEM_CAMINHO` | nao ha subnet compartilhada nem rota |
| `TESTE_BLOQUEADO_POR_ACL` | o caminho existe e uma ACL fecha |

Testar so o caminho feliz deixa passar codigo que aprova rota inexistente, que
e o tipo de bug que so aparece quando o servico ja esta fora do ar.

## O que este estagio prova, e o que nao prova

Prova que, **segundo a configuracao escrita**, o caminho existe. Se a VLAN 20
esta isolada e sem rota para a VLAN 10, o pacote nao chega - e isso nao
depende de o equipamento estar ligado.

Nao prova que a configuracao seja aceita pelo equipamento, que o hardware
suporte o que foi pedido, nem que exista performance. Um arquivo pode passar
aqui e ser rejeitado no primeiro `commit` do equipamento.

Isso nao e defeito do simulador: e o limite do que da para saber sem o
equipamento. E por isso que o estagio nunca diz "funciona" - diz "o caminho
existe segundo o plano". Ver `docs/o-que-bloquear-em-ci.md`.

## O padrao implicito da ACL

A ACL numerada tem comportamento implicito, e ele e **permitir**. Uma ACL que
lista `permit` e nao termina em `deny ip any any` deixa passar tudo que nao
foi listado. E verdade no equipamento, e e a razao de o estagio de regras ter
uma regra propria para isso.

Aqui o mesmo padrao vale: a ausencia de `deny` significa que o caminho passa.
Um teste que tratasse ausencia de regra como bloqueio reprovaria a maioria
dos arquivos corretos.

## O laboratorio nao simula inspecao de pacote

So o `deny ip any any` fecha o caminho. Um `deny` especifico, como
`deny ip any any eq 23`, nao fecha o trafego de outros portos, e tratar todo
`deny` como bloqueio reprovaria configuracao correta. A regra e
deliberadamente grossa, e o motivo esta aqui para ninguem "consertar" depois.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from .achado import AVISO, ERRO, Achado
from .parser import Configuracao

ESTAGIO = "testes"


@dataclass(frozen=True)
class Alvo:
    """Um ponto com endereco na rede.

    A point with an address on the network.

    Attributes:
        nome: Como o alvo e chamado na linha de comando.
        endereco: O endereco IPv4.
    """

    nome: str
    endereco: str

    @property
    def ip(self) -> ipaddress.IPv4Address:
        """O endereco como objeto do modulo ipaddress.

        The address as an ipaddress object.

        Returns:
            O endereco convertido.
        """
        return ipaddress.IPv4Address(self.endereco)


@dataclass(frozen=True)
class RegraTeste:
    """Uma regra do estagio de teste.

    A rule of the test stage.

    Attributes:
        codigo: Identificador estavel.
        descricao: O que a regra checa.
    """

    codigo: str
    descricao: str


REGRAS = (
    RegraTeste("TESTE_SEM_CAMINHO", "nao ha rota nem subnet compartilhada"),
    RegraTeste("TESTE_BLOQUEADO_POR_ACL", "o caminho existe mas uma ACL nega"),
    RegraTeste("TESTE_OK", "o caminho existe e nenhuma ACL nega"),
)


def tabela() -> list[RegraTeste]:
    """As regras que este estagio avalia.

    The rules this stage evaluates.

    Returns:
        A lista de regras.
    """
    return list(REGRAS)


def _prefixos(config: Configuracao) -> list[ipaddress.IPv4Network]:
    """As redes declaradas nas interfaces.

    The networks declared on the interfaces.

    Uma linha `ip address` sem mascara, ou com mascara invalida, e ignorada
    em silencio. A alternativa - estourar erro - transformaria um problema de
    inventario em uma falha de estagio que nao tem a ver com conectividade, e
    quem	this`` precisaria ler dois achados para entender um erro.

    Args:
        config: A configuracao parseada.

    Returns:
        As redes validas encontradas.
    """
    redes: list[ipaddress.IPv4Network] = []
    for interface in config.interfaces:
        for subcomando in interface.subcomandos:
            if subcomando.nome != "ip" or subcomando.tokens()[:1] != ["address"]:
                continue
            partes = subcomando.tokens()
            if len(partes) < 3:
                continue
            try:
                ipaddress.IPv4Address(partes[1])
                redes.append(
                    ipaddress.IPv4Network(
                        f"{partes[1]}/{partes[2]}", strict=False
                    )
                )
            except (ipaddress.AddressValueError, ipaddress.NetmaskValueError):
                continue
    return redes


def _mesma_subnet(
    origem: str,
    destino: str,
    redes: list[ipaddress.IPv4Network],
) -> ipaddress.IPv4Network | None:
    """A rede que os dois enderecos compartilham, se houver.

    The network both addresses share, if any.

    `endereco in rede` exige um objeto `IPv4Address`, nao uma string: o modulo
    `ipaddress` compara versao e so aceita o objeto. Passar a string quebra em
    tempo de execucao, e nao na montagem.

    Args:
        origem: Endereco de origem.
        destino: Endereco de destino.
        redes: As redes declaradas.

    Returns:
        A rede compartilhada, ou `None`.
    """
    origem_ip = ipaddress.IPv4Address(origem)
    destino_ip = ipaddress.IPv4Address(destino)
    for rede in redes:
        if origem_ip in rede and destino_ip in rede:
            return rede
    return None


def _linha_da_rota(config: Configuracao, destino: str) -> int | None:
    """Se existe rota para o destino, e em que linha.

    Whether a route to the destination exists, and on which line.

    Args:
        config: A configuracao parseada.
        destino: Endereco de destino.

    Returns:
        A linha da rota, ou `None`.
    """
    alvo = ipaddress.IPv4Address(destino)
    for comando in config.comandos:
        if comando.nome != "ip":
            continue
        partes = comando.tokens()
        if partes[:1] != ["route"] or len(partes) < 4:
            continue
        try:
            rede = ipaddress.IPv4Network(f"{partes[1]}/{partes[2]}", strict=False)
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError):
            continue
        # prefixlen 0 e a rota padrao: alcanca qualquer destino.
        if rede.prefixlen == 0 or alvo in rede:
            return comando.linha
    return None


def _nega_tudo(config: Configuracao) -> tuple[int, str] | None:
    """A negacao implicita, se o arquivo tem uma.

    The implicit deny, if the file has one.

    Args:
        config: A configuracao parseada.

    Returns:
        ``(linha, regra)`` da negacao, ou `None`.
    """
    for comando in config.comandos:
        if comando.nome != "access-list":
            continue
        partes = comando.tokens()
        if len(partes) >= 2 and partes[1] == "deny" and partes[2:] == ["ip", "any", "any"]:
            return comando.linha, " ".join(partes[1:])
    return None


def testar(config: Configuracao, origem: str, destino: str) -> list[Achado]:
    """Se o caminho entre dois enderecos existe.

    Whether the path between two addresses exists.

    Args:
        config: A configuracao parseada.
        origem: Endereco de origem, em notacao IPv4.
        destino: Endereco de destino, em notacao IPv4.

    Returns:
        Exatamente um achado: `TESTE_OK`, `TESTE_SEM_CAMINHO` ou
        `TESTE_BLOQUEADO_POR_ACL`.
    """
    redes = _prefixos(config)
    subnet = _mesma_subnet(origem, destino, redes)
    linha_rota = _linha_da_rota(config, destino)

    if subnet is None and linha_rota is None:
        return [
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="TESTE_SEM_CAMINHO",
                mensagem=(
                    f"sem caminho de {origem} para {destino}: "
                    "nenhuma subnet compartilhada e nenhuma rota"
                ),
                linha=0,
                sugestao="declare uma rota ou uma interface na rede de destino",
            )
        ]

    negacao = _nega_tudo(config)
    if negacao is not None:
        linha, regra = negacao
        return [
            Achado(
                estagio=ESTAGIO,
                severidade=ERRO,
                codigo="TESTE_BLOQUEADO_POR_ACL",
                mensagem=(
                    f"caminho de {origem} para {destino} existe mas a ACL "
                    f"nega tudo: {regra}"
                ),
                linha=linha,
                sugestao="a negacao implicita fecha o caminho antes do destino",
            )
        ]

    descricao = (
        f"subnet {subnet}"
        if subnet is not None
        else f"rota declarada na linha {linha_rota}"
    )
    return [
        Achado(
            estagio=ESTAGIO,
            severidade=AVISO,
            codigo="TESTE_OK",
            mensagem=f"caminho de {origem} para {destino} existe ({descricao})",
            linha=linha_rota or 0,
        )
    ]


def alvos_padrao() -> list[Alvo]:
    """Os alvos que o laboratorio nomeia por convencao.

    The targets the lab names by convention.

    A convencao existe para o comando poder ser curto na documentacao. Todo
    endereco e RFC 1918.

    Returns:
        Os alvos conhecidos.
    """
    return [
        Alvo("gerencia", "192.168.30.2"),
        Alvo("servidor", "192.168.20.10"),
        Alvo("estacao", "192.168.10.10"),
        Alvo("visitante", "192.168.40.10"),
    ]