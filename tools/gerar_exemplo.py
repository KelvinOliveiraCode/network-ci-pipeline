"""Gera o exemplo de relatorio a partir da saida real do pipeline.

Generate the report example from the pipeline's real output.

O exemplo vai para o repositorio para ser lido sem instalar nada, entao ele
precisa ser a saida de verdade e nao uma transcricao. A alternativa - colar
a saida a mao - envelhece: o codigo muda, o exemplo nao, e o exemplo passa a
descrever um pipeline que nao existe mais.

Por isso o exemplo e GERADO, e o CI compara o arquivo do repositorio com o que
este script produz agora. Divergencia derruba o build.

Nao ha timestamp nem caminho absoluto em nada aqui, para que o arquivo seja
identico em qualquer maquina.
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from netci.cli import main as cli_main  # noqa: E402

GOLDEN = "dados/golden/switch-core.cfg"
CANDIDATOS = "dados/candidatos"

DESTINO = RAIZ / "exemplos" / "relatorio-ci.md"


def roda(argv: list[str]) -> tuple[int, str]:
    """Roda a CLI e devolve o codigo e a saida.

    Run the CLI and return the code and the output.

    Args:
        argv: Os argumentos.

    Returns:
        O par ``(codigo_de_saida, saida)``.
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        codigo = cli_main(argv)
    return codigo, buffer.getvalue().rstrip("\n")


def bloco(titulo: str, comando: str, argv: list[str], nota: str = "") -> list[str]:
    """Uma secao com a saida real de um comando.

    A section with the real output of a command.

    Args:
        titulo: O titulo da secao.
        comando: O comando, para o leitor copiar.
        argv: Os argumentos reais.
        nota: Uma frase sobre o que a saida mostra.

    Returns:
        As linhas da secao.
    """
    codigo, saida = roda(argv)
    linhas = [
        f"## {titulo}",
        "",
        f"Comando: `{comando}`",
        "",
        f"Saida (codigo de saida `{codigo}`):",
        "",
        "```",
        saida,
        "```",
        "",
    ]
    if nota:
        linhas.extend([nota, ""])
    return linhas


def principal() -> int:
    """Regera o exemplo e grava no destino.

    Regenerate the example and write it to the destination.

    Returns:
        Sempre 0.
    """
    partes: list[str] = [
        "# Relatorios do pipeline",
        "",
        "Os blocos abaixo sao a saida real do `netci`, copiada sem edicao por",
        "`tools/gerar_exemplo.py`. Por isso o exemplo serve como prova do",
        "comportamento em vez de descricao dele: se o pipeline mudar e este",
        "arquivo nao acompanhar, o `git diff --exit-code` do CI falha.",
        "",
        "Para reproduzir localmente:",
        "",
        "```powershell",
        "python tools/gerar_exemplo.py",
        "```",
        "",
    ]

    partes += bloco(
        "Reprovado no estagio de sintaxe",
        f"python -m netci validar {CANDIDATOS}/switch-ruins-sintaxe.cfg --golden {GOLDEN}",
        ["validar", f"{CANDIDATOS}/switch-ruins-sintaxe.cfg", "--golden", GOLDEN],
        "Um `trun` onde se queria `trunk`. Os tres estagios seguintes aparecem "
        "marcados como nao executados: o pipeline parou, e o relatorio diz "
        "qual foi o motivo da parada. Uma estagio que passou e um estagio que "
        "nao rodou sao coisas diferentes, e a diferenca esta escrita no "
        "proprio relatorio.",
    )

    partes += bloco(
        "Reprovado no estagio de regras de negocio",
        f"python -m netci validar {CANDIDATOS}/switch-ruins-regras.cfg --golden {GOLDEN}",
        ["validar", f"{CANDIDATOS}/switch-ruins-regras.cfg", "--golden", GOLDEN],
        "Este arquivo passa na sintaxe e reprova em negocio: VLAN duplicada, "
        "rota padrao duplicada e ACL sem o `deny` final. Sao tres problemas "
        "independentes, e os tres aparecem com linha e com a sugestao de "
        "correcao.",
    )

    partes += bloco(
        "Aprovado com avisos",
        f"python -m netci validar {CANDIDATOS}/switch-ok-2.cfg --golden {GOLDEN}",
        ["validar", f"{CANDIDATOS}/switch-ok-2.cfg", "--golden", GOLDEN],
        "A VLAN 50 nao existe na referencia. Isso e aviso e nao erro: uma "
        "VLAN nova e mudanca legitima, e o estagio nao e dono da decisao de "
        "aceita-la. O merge passa, e o revisor ve que ela existe.",
    )

    partes += bloco(
        "Teste de conectividade, quando pedido",
        f"python -m netci validar {CANDIDATOS}/switch-ok-1.cfg --golden {GOLDEN} "
        "--origem 192.168.30.2 --destino 192.168.30.9",
        [
            "validar", f"{CANDIDATOS}/switch-ok-1.cfg", "--golden", GOLDEN,
            "--origem", "192.168.30.2", "--destino", "192.168.30.9",
        ],
        "O caminho entre os dois enderecos existe, porque os dois estao na "
        "subnet que a interface Vlan30 declara. A ACL numerada do arquivo "
        "termina em `deny ip any any`, e essa negacao implicita fecha o "
        "caminho. O estagio prova logica de enderecamento e nada alem disso.",
    )

    partes += bloco(
        "O pipeline inteiro de uma vez",
        f"python -m netci pipeline {CANDIDATOS} --golden {GOLDEN}",
        ["pipeline", CANDIDATOS, "--golden", GOLDEN],
        "A leitura que interessa vem primeiro: o veredito de cada candidato "
        "lado a lado, e so depois o detalhe de quem foi reprovado. Quem "
        "aprovado aparece em uma linha porque nao ha nada a ler sobre ele.",
    )

    partes += bloco(
        "As regras do pipeline",
        "python -m netci regras",
        ["regras"],
        "Todos os codigos de regra, por estagio. O codigo e estavel de "
        "proposito: CI precisa ser compativel, e um alerta que muda de nome a "
        "cada versao faz o historico do pipeline deixar de fazer sentido.",
    )

    partes += [
        "## Como ler um relatorio vermelho",
        "",
        "O relatorio traz quatro coisas por achado: a linha, o codigo da "
        "regra, o que aconteceu e como corrigir. A correcao sugerida vem "
        "das regras e nao do relatorio, e por isso ela e acionavel.",
        "",
        "Os achados vem em ordem de gravidade, e nao de linha: quem tem "
        "quarenta avisos e um erro precisa ver o erro primeiro.",
        "",
        "Um estagio que aparece como `nao rodou` nao passou. Ele tem duas "
        "causas possiveis, e o relatorio distingue as duas: o estagio "
        "anterior reprovou, ou o estagio nao foi pedido. A segunda aparece "
        "quando o teste de conectividade nao tem `--origem` e `--destino`, e "
        "e o caso em que o pipelineApproved e o teste de conectividade "
        "simplesmente nao aconteceu.",
        "",
    ]

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text("\n".join(partes), encoding="utf-8", newline="\n")
    print(f"exemplo gravado em {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())