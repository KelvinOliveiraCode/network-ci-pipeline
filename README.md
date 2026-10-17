<img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
<img src="https://img.shields.io/badge/testes-183%20passing-brightgreen?style=flat-square" alt="Testes">
<img src="https://img.shields.io/badge/cobertura-95%25-green?style=flat-square" alt="Cobertura">
<img src="https://img.shields.io/badge/dependencias-zero%20de%20execucao-brightgreen?style=flat-square" alt="Dependencias">
<img src="https://img.shields.io/badge/licenca-MIT-yellow?style=flat-square" alt="Licenca">
<img src="https://img.shields.io/badge/plataforma-independente-blue?style=flat-square" alt="Plataforma">

# network-ci-pipeline

Pipeline local de CI que valida arquivos de configuracao de rede antes de aplicar em equipamento: sintaxe, regras de negocio, golden config, teste de conectividade simulado e relatorio. O pacote tem zero dependencias de execucao e nao fala com equipamento nenhum.

## Problema / Por que existe

Scripts de configuracao de rede quebram em servico, e quase sempre por tres erros que nenhum deles pega: uma palavra digitada errado, um comando sem o deny final e uma VLAN declarada duas vezes. Nenhum e dificil de detectar. Todos sao impossiveis de detectar depois do estrago.

Este pipeline existe para ser o lugar onde esses erros acontecem sem consequencia: e um gate que impede que uma configuracao invalida chegue ao equipamento. O argumento mais forte de quem automatiza infraestrutura nao e "automatizei", e "tenho um gate que impede isso de chegar no equipamento".

Nada aqui e real. SW-CORE-LAB nao existe. As configuracoes usam sintaxe Cisco-like escrita para este projeto, e nao ha SSH, SNMP, socket nem SDK de equipamento em lugar nenhum.

## O que faz

Le um arquivo .cfg de switch e diz o que esta errado com ele, parando no primeiro estagio que reprova. O codigo de saida e 0 quando o candidato pode seguir para o merge, e diferente de zero quando nao pode.

Os estagios executam nesta ordem:

1. sintaxe — o arquivo faz sentido como texto? (vocabulario, tipos, limites)
2. regras — faria sentido no laboratorio? (coerencia de inventario)
3. golden — continua estruturalmente completo? (presenca do que nao pode faltar, contra a configuracao de referencia)
4. testes — o caminho existe? (aritmetica de endereçamento, logica de caminho)
5. relatorio — o que aconteceu? (texto para gente, JSON para maquina)

Saida para um candidato com erro de sintaxe:

```
========================================================================
CI DE REDE - dados/candidatos/switch-ruins-sintaxe.cfg
========================================================================

ESTAGIOS
  sintaxe    1 erro(s), 0 aviso(s)
  regras     nao rodou (estagio anterior reprovou)
  golden     nao rodou (estagio anterior reprovou)
  testes     nao rodou (nao solicitado: use --origem e --destino)

INTERRUPIDO EM: sintaxe
Os estagios seguintes dependem deste e nao foram executados.
Corrigir o achado acima e rodar de novo.

ACHADOS
  [ERRO ] VALOR_INVALIDO
  onde: linha 56
  o que: modo de porta invalido: 'trun'; aceitos: access, dot1q-tunnel, dynamic, trunk
  como corrigir: em Gi0/2, 'trun' quase sempre quer dizer 'trunk'

========================================================================
RESULTADO: REPROVADO
1 erro(s) bloqueiam o merge. O candidato nao pode ser aplicado.
```

Todos os cinco candidatos de uma vez:

```
python -m netci pipeline dados/candidatos --golden dados/golden/switch-core.cfg
```

```
APROVADO             0 erro(s)  0 aviso(s)  switch-ok-1.cfg
APROVADO COM AVISOS  0 erro(s)  1 aviso(s)  switch-ok-2.cfg
APROVADO             0 erro(s)  0 aviso(s)  switch-ok-3.cfg
REPROVADO            3 erro(s)  0 aviso(s)  switch-ruins-regras.cfg
REPROVADO            1 erro(s)  0 aviso(s)  switch-ruins-sintaxe.cfg
```

Duas severidades, declaradas no codigo de cada regra e herdadas pelo relatorio:

| Severidade | Efeito |
| ERRO | bloqueia o merge |
| AVISO | nao bloqueia, desvio que o revisor precisa ver |

O golden config nao compara igualdade. Se comparasse o candidato com a referencia como igualdade, toda mudança legítima seria reprovada e o time aprenderia a aprovar sem ler. A comparacao e sobre o que nao pode faltar em nenhuma configuracao saudavel: enable secret, bloco line vty com senha, deny ip any any no final da ACL, spanning-tree mode e pelo menos um trunk. O que existe só no golden nao e achado: uma VLAN a mais e aviso e passa, uma interface a menos nao e erro.

## Stack

- Python 3.10+
- Biblioteca padrão apenas: argparse, dataclasses, ipaddress, pathlib. Nenhuma biblioteca de rede, SSH ou SDK de equipamento.
- Desenvolvimento: pytest>=7.4, pytest-cov>=4.1
- Empacotamento: setuptools, `pip install -e ".[dev]"`
- CI: GitHub Actions, windows-latest, Python 3.11 (.github/workflows/ci.yml)

## Como funciona

O modulo pipeline decide a ordem dos estagios e para no primeiro que acha algum ERRO. Nenhum estagio sabe que os outros existem.

| Modulo | Responsabilidade |
| parser.py | Le o arquivo em comandos, blocos de interface e blocos line |
| achado.py | Tipo unico de todos os estagios, com severidade |
| sintaxe.py | Estagio 1 — vocabulario, tipos e limites |
| regras.py | Estagio 2 — coerencia de inventario |
| golden.py | Estagio 3 — presença do que e estrutural |
| testes.py | Estagio 4 — aritmetica de endereçamento |
| pipeline.py | Ordem dos estagios e regra de parada |
| relatorio.py | Texto para gente, JSON para maquina |
| cli.py | validar, pipeline, regras |

Regra de parada: o pipeline para no primeiro estagio com ERRO. A excecao e o estagio de regras, que roda mesmo quando a sintaxe reprova. VLAN duplicada e trun torto sao erros concorrentes, nao dependentes: o segundo achado existe independente do primeiro, entao vale rodar. Se o segundo e consequencia do primeiro, o pipeline para.

Os achados vem em ordem de gravidade, nao de linha: quem tem quarenta avisos e um erro precisa ver o erro primeiro. Um estagio que aparece como nao rodou diz por que, em dois casos distintos: estagio anterior reprovou, ou nao foi solicitado.

## Como rodar

Instalacao:

```
pip install -e ".[dev]"
```

Validar um candidato:

```
python -m netci validar dados/candidatos/switch-ruins-sintaxe.cfg --golden dados/golden/switch-core.cfg
```

Validar todos os candidatos de uma pasta:

```
python -m netci pipeline dados/candidatos --golden dados/golden/switch-core.cfg
```

Listar as 24 regras por estagio:

```
python -m netci regras
```

Rodar os testes:

```
python -m pytest
```

A suíte tem 183 testes passando e cobertura de 95%. O piso de 70% e imposto em pyproject.toml; abaixo disso o build cai.

## Estrutura do projeto

```
network-ci-pipeline/
├── src/netci/            codigo fonte do pacote netci
├── dados/candidatos/     cinco arquivos .cfg para validar
├── dados/golden/         configuracao de referencia switch-core.cfg
├── tests/                183 testes (parser, estagios, pipeline, relatorio, CLI, portao de encoding)
├── tools/                verificar_aceite.py, verificar_encoding.py, gerar_exemplo.py
├── docs/                 regras-de-ci-em-rede.md, o-que-bloquear-em-ci.md
├── exemplos/relatorio-ci.md  exemplo de relatorio gerado pelo pipeline
├── .github/workflows/ci.yml  CI no GitHub Actions
├── pyproject.toml        configuracao do pacote, piso de cobertura 70%
├── requirements.txt      dependencias de desenvolvimento
└── LICENSE               MIT
```

## Trade-offs e decisoes

- Parar no primeiro ERRO custa informacao (um relatorio com um problema em vez de sete), mas evita que um erro de sintaxe vire falsos problemas de negocio nos estagios seguintes.
- O estagio de regras roda depois de sintaxe reprovar porque os problemas sao concorrentes, nao dependentes: corrigir um nao faz o outro desaparecer.
- Golden config nao e igualdade estrita: mudancas legítimas (VLAN nova, interface a mais) nao podem reprovar; o que falta so na referencia e aviso, nao erro.
- Blocos sao delimitados por indentacao, nao por exit. Configuracao de equipamento raramente fecha bloco com exit, e exigir exit reprovaria configuracao real.
- Codigo de saida 0 tambem com avisos: aviso nao bloqueia o merge. Apenas ERRO retorna 1; erro de leitura retorna 2.
- Um candidato por execucao. O comando pipeline roda uma pasta, mas avalia cada arquivo de forma independente, sem comparacao entre candidatos.

## Limitações conhecidas

- A sintaxe e Cisco-like fictícia. Os arquivos sao plausíveis, nao sao saída real de nenhum produto. Um equipamento real exige um parser reescrito.
- Nao fala com equipamento: sem SSH, SNMP, socket ou SDK. Nao verifica se o equipamento aceita a configuracao, se o hardware suporta o pedido nem a compatibilidade de versao do sistema.
- O teste de conectividade nao simula inspecao de pacote. Todo deny nao fecha o caminho; apenas deny ip any any fecha. E aritmetica de endereço IPv4, nao dados de runtime.
- A ACL e avaliada na entrada, globalmente. O laboratorio nao modela direcao, interface de aplicacao nem ordem de avaliacao.
- O vocabulario e fechado e pequeno. Um comando fora da lista vira erro. Para equipamentos de varios fabricantes, a lista precisaria crescer e a decisão erro vs aviso para linha desconhecida teria de ser retomada a cada equipamento novo.
- Um candidato por execucao. Nao ha validacao em lote além do pipeline, nem comparacao entre candidatos.
- Um arquivo pode passar aqui e ser rejeitado no primeiro commit do equipamento.

## Licença

MIT.

## Autor

Kelvin Oliveira
