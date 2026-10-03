<div align="center">

<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/tests-183%20passing-brightgreen?style=flat-square" alt="Tests">
  <img src="https://img.shields.io/badge/coverage-95%25-brightgreen?style=flat-square" alt="Coverage">
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/platform-Windows-blue?style=flat-square" alt="Windows">
</p>

</div>

# network-ci-pipeline

Pipeline local de CI que valida arquivos de configuração de rede **antes** de
aplicar em equipamento: sintaxe, regras de negócio, golden config, teste de
conectividade simulado e relatório.

A local CI pipeline that validates network configuration files **before**
applying them to a device: syntax, business rules, golden config, simulated
connectivity test and report.

> **Nada aqui é real.** `SW-CORE-LAB` não existe. As configurações usam
> sintaxe Cisco-like escrita para este projeto, e não há SSH, SNMP, socket nem
> SDK de equipamento em lugar nenhum. O pacote tem **zero dependência de
> execução**.

## O que é

Cinco estágios que leem uma configuração de switch e dizem o que está errado
com ela, parando no primeiro que reprovar. O código de saída é 0 quando o
candidato pode seguir para o merge, e diferente de zero quando não pode.

## Por que foi feito

A maior parte dos scripts de configuração quebra em serviço, e quase sempre
por três motivos que nenhum deles pegava: uma palavra digitada errado, um
comando sem o `deny` final, e uma VLAN declarada duas vezes.

Nenhum desses é difícil de detectar. Todos são **impossíveis de detectar depois
do estrago**, e o pipeline de CI em rede existe para ser o lugar onde eles
acontecem sem consequência.

O argumento mais forte de quem automatiza infraestrutura não é "eu automatizei",
é "eu tenho um gate que impede isso de chegar no equipamento".

## Como rodar

Um comando, saída esperada:

```powershell
python -m netci validar dados/candidatos/switch-ruins-sintaxe.cfg --golden dados/golden/switch-core.cfg
```

```
========================================================================
CI DE REDE - dados/candidatos/switch-ruins-sintaxe.cfg
========================================================================

ESTAGIOS
  sintaxe    1 erro(s), 0 aviso(s)
  regras     nao rodou (estagio anterior reprovou)
  golden     nao rodou (estagio anterior reprovou)
  testes     nao rodou (nao solicitado: use --origem e --destino)

INTERROMPIDO EM: sintaxe
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

Os cinco candidatos de uma vez:

```powershell
python -m netci pipeline dados/candidatos --golden dados/golden/switch-core.cfg
```

```
APROVADO             0 erro(s)  0 aviso(s)  switch-ok-1.cfg
APROVADO COM AVISOS  0 erro(s)  1 aviso(s)  switch-ok-2.cfg
APROVADO             0 erro(s)  0 aviso(s)  switch-ok-3.cfg
REPROVADO            3 erro(s)  0 aviso(s)  switch-ruins-regras.cfg
REPROVADO            1 erro(s)  0 aviso(s)  switch-ruins-sintaxe.cfg
```

Instalação:

```powershell
pip install -e ".[dev]"
```

## Os cinco estágios

| # | Estágio | Pergunta | Regras |
|---|---|---|---|
| 1 | `sintaxe` | isto faz sentido como texto? | 7 |
| 2 | `regras` | faria sentido no laboratório? | 7 |
| 3 | `golden` | continua estruturalmente completo? | 7 |
| 4 | `testes` | o caminho existe? | 3 |
| 5 | `relatório` | o que aconteceu? | — |

24 regras no total, todas com código estável:

```powershell
python -m netci regras
```

## Por que o pipeline para no primeiro que reprova

A tentação é rodar tudo e juntar os erros, achando que um relatório com sete
problemas é mais útil que um com um. É o oposto.

Erro de sintaxe muda a leitura de tudo que vem depois. Um `trun` que ninguém
reconhece faz a regra de negócio não encontrar a porta access que deveria
estar ali, e o relatório passa a listar como problema de negócio algo que é
consequência do problema de sintaxe.

**A exceção é o estágio de regras**, que roda mesmo quando a sintaxe reprova.
Os dois problemas são *concorrentes*, não *dependentes*: a VLAN duplicada
existe independentemente do `trun` torto. A linha que separa os dois casos é
simples — **o segundo achado existe independentemente do primeiro?**

## O golden config não compara igualdade

É a tentação mais fácil de cair e a mais destrutiva. Se o golden config
comparasse o candidato com a referência como igualdade, **toda mudança
legítima seria reprovada** — e o time aprenderia a aprovar sem ler, que é
exatamente o que um pipeline existe para evitar.

A comparação é sobre o que **não pode faltar** em nenhuma configuração
saudável: `enable secret`, bloco `line vty` com senha, o `deny ip any any`
final da ACL, `spanning-tree mode` e pelo menos um trunk.

O que existe só no golden **não é achado**. Uma VLAN a mais é aviso e passa;
uma interface a menos não é erro. São decisões do revisor, e o estágio não é
dono delas.

## Duas severidades

| Severidade | Efeito | Quando |
|---|---|---|
| `ERRO` | bloqueia o merge | derruba serviço, abre acesso que estava fechado |
| `AVISO` | não bloqueia | desvio que o revisor precisa ver |

A separação está **no código**, não no texto: cada regra declara sua severidade
e o relatório só herda. Um pipeline que bloqueia por tudo treina o time a
ignorar o vermelho; um pipeline que nunca bloqueia não é CI.

`docs/o-que-bloquear-em-ci.md` discute esse equilíbrio em detalhe.

## O que o relatório garante

Quatro coisas por achado: **linha, código da regra, o que aconteceu e como
corrigir**. A sugestão vem da regra, não do relatório, e por isso é acionável.

Os achados vêm em ordem de gravidade, não de linha: quem tem quarenta avisos e
um erro precisa ver o erro primeiro.

E um estágio que aparece como `não rodou` diz **por quê**, em dois casos
distintos:

```
testes     nao rodou (nao solicitado: use --origem e --destino)
```

Sem essa distinção o relatório afirma que o pipeline parou num estágio que
passou — e quem lê conclui que o teste de conectividade foi verificado quando
não foi.

## O que este pipeline **não** verifica

- performance, e nem se a configuração é aceita pelo equipamento;
- se o hardware suporta o que foi pedido;
- compatibilidade de versão de IOS;
- o estado real do equipamento.

O teste de conectividade prova **lógica de enderecamento**: se a VLAN 20 está
isolada e sem rota para a VLAN 10, o pacote não chega — e isso não depende de
o equipamento estar ligado. Ele não abre socket, não resolve nome e não
simula inspeção de pacote: só o `deny ip any any` fecha o caminho, e isso é
deliberado e está documentado no código.

Um arquivo pode passar aqui e ser rejeitado no primeiro `commit`.

## Como funciona

| Módulo | Responsabilidade |
|---|---|
| `parser.py` | Lê o arquivo em comandos, blocos de interface e blocos `line` |
| `achado.py` | O tipo único de todos os estágios, com severidade |
| `sintaxe.py` | Estágio 1 — vocabulário, tipos e limites |
| `regras.py` | Estágio 2 — coerência de inventário |
| `golden.py` | Estágio 3 — presença do que é estrutural |
| `testes.py` | Estágio 4 — aritmética de endereçamento |
| `pipeline.py` | A ordem dos estágios e a regra de parada |
| `relatorio.py` | Texto para gente, JSON para máquina |
| `cli.py` | `validar`, `pipeline`, `regras` |

### O parser usa indentação, não `exit`

Configuração de equipamento raramente fecha bloco com `exit`. As três
alternativas que pareciam corretas estavam erradas: exigir `exit` reprova
configuração real; fechar o bloco no próximo `interface` resolve interfaces e
deixa `line vty` engolindo o resto do arquivo; e inferir o fim do bloco pelo
vocabulário é conhecimento de validação dentro do parser.

**A indentação é o sinal**, e é o que o equipamento usa.

### O relatório tem dois formatos, não um

Quem lê no terminal e o script que decide o merge têm requisitos opostos. Servir
os dois com um formato só significa quebrar um deles. Então: texto no stdout,
ordenado por gravidade e com o número de linha; JSON em arquivo, com a
severidade de cada achado.

## Testes

```powershell
python -m pytest -v
```

183 testes, 95% de cobertura, 24 regras. Cobrem o parser (blocos, indentação,
`line vty`), os quatro estágios, o pipeline e a regra de parada, o relatório em
texto e JSON, a CLI inteira incluindo o código de saída, e o portão de encoding
plantando um ideograma de verdade para provar que o portão sobrevive ao que ele
detecta.

Portões que a suíte não cobre sozinha:

```powershell
python tools/verificar_aceite.py     # as duas metades do critério de aceite
python tools/verificar_encoding.py   # nenhum caractere corrompido
python tools/gerar_exemplo.py        # regenera o exemplo de forma determinística
```

```
1) os cinco candidatos tem o veredito esperado
   switch-ok-1.cfg              APROVADO
   switch-ok-2.cfg              APROVADO
   switch-ok-3.cfg              APROVADO
   switch-ruins-regras.cfg      REPROVADO em regras
   switch-ruins-sintaxe.cfg     REPROVADO em sintaxe

2) os dois reprovados falham por motivos distintos
   switch-ruins-regras.cfg: ['ACL_SEM_DENY', 'ROTA_PADRAO_DUPLICADA', 'VLAN_DUPLICADA']
   switch-ruins-sintaxe.cfg: ['VALOR_INVALIDO']

3) a regra de parada: estagios depois da falha nao rodam
   switch-ruins-regras.cfg: rodou ['sintaxe', 'regras'], parou em regras
   switch-ruins-sintaxe.cfg: rodou ['sintaxe'], parou em sintaxe

4) o codigo de saida reflete o veredito
   switch-ok-1.cfg              saida=0
   switch-ok-2.cfg              saida=0
   switch-ruins-sintaxe.cfg     saida=1
   switch-ruins-regras.cfg      saida=1
   pipeline completo                saida=1

ok: os 5 candidatos classificados certo, os 2 reprovados por motivos distintos, parada no primeiro estagio que falha, e codigo de saida correto
```

A metade 2 é a que importa: dois arquivos reprovados pela **mesma** regra
provariam que o estágio pega um problema, duas vezes.

## Limitações

- **A sintaxe é Cisco-like fictícia.** Os arquivos são plausíveis, não são a
  saída real de nenhum produto. Um equipamento real exige um parser reescrito.
- **O teste de conectividade não simula inspeção de pacote.** Todo `deny` não
  fecha o caminho; só o `deny ip any any` fecha. Tratar qualquer `deny` como
  bloqueio reprovaria configuração correta.
- **A ACL é avaliada na entrada, globalmente.** O laboratório não modela
  direção, interface de aplicação nem ordem de avaliação. Uma ACL real é
  avaliada de forma bem diferente.
- **Nenhuma verificação de rede.** Ver a seção acima; é a limitação que mais
  importa e a que é mais fácil de esconder.
- **O vocabulário é fechado e pequeno.** Comando fora da lista vira erro. Num
  laboratório com equipamentos de vários fabricantes isso precisaria crescer,
  e a escolha entre `erro` e `aviso` para linha desconhecida é uma decisão que
  teria de ser tomada de novo a cada equipamento novo.
- **Um candidato por execução.** Não há validação em lote além do `pipeline`,
  nem comparação entre candidatos.

## Licença

MIT.

---

## English

A local CI pipeline that validates network configuration files **before**
applying them to a device: syntax, business rules, golden config, simulated
connectivity test and report.

Nothing here is real. There is no SSH, SNMP, socket or device SDK; the package
has zero runtime dependencies.

### The five stages

| # | Stage | Question | Rules |
|---|---|---|---|
| 1 | `sintaxe` | does this make sense as text? | 7 |
| 2 | `regras` | would it make sense in the lab? | 7 |
| 3 | `golden` | is it still structurally complete? | 7 |
| 4 | `testes` | does the path exist? | 3 |
| 5 | `relatório` | what happened? | — |

The pipeline stops at the first stage that rejects. The exception is the
business-rules stage, which runs even after syntax fails: the two problems are
*concurrent*, not *dependent*. The line separating them is simple — **does the
second finding exist independently of the first?**

### Golden config is not an equality check

This is the easiest trap to fall into and the most destructive. If the golden
config compared candidate against reference as equality, **every legitimate
change would be rejected** — and the team would learn to approve without
reading, which is exactly what a pipeline exists to prevent.

The comparison is about what **cannot be missing**: `enable secret`, a `line
vty` block with a password, the final `deny ip any any`, `spanning-tree mode`,
and at least one trunk. What exists only in the golden is **not a finding**. A
new VLAN is a warning and passes; a missing interface is not an error.

### Two severities

`ERRO` blocks the merge; `AVISO` does not. The separation lives **in the code**,
not in the documentation: each rule declares its severity and the report only
inherits. `docs/o-que-bloquear-em-ci.md` argues the balance.

### What this pipeline does **not** verify

Performance, whether the device accepts the configuration, hardware support,
IOS version compatibility, or the device's real state. The connectivity test
proves **addressing logic** and nothing more: if VLAN 20 is isolated with no
route to VLAN 10, the packet does not arrive — and that does not depend on the
device being powered on.

### Tests

183 tests, 95% coverage.

```powershell
python -m pytest -v
python tools/verificar_aceite.py
python tools/verificar_encoding.py
python tools/gerar_exemplo.py
```

The acceptance proof checks that the five candidates are classified correctly,
that the two rejected ones fail for **distinct** reasons, that stages after a
failure do not run, and that the exit code reflects the verdict.

### Limitations

- **Fictitious Cisco-like syntax.** Plausible, not any product's real output.
- **No packet inspection.** Any `deny` does not close the path; only
  `deny ip any any` does.
- **ACLs are evaluated once, globally.** No direction, no ingress interface, no
  evaluation order.
- **No network verification at all** — the limitation most easily hidden.
- **A closed, small vocabulary.** An unknown command is an error; growing this
  for a multi-vendor lab means re-deciding that choice per new device.
- **One candidate per run**, aside from the `pipeline` command.

### License

MIT.