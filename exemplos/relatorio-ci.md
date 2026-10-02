# Relatorios do pipeline

Os blocos abaixo sao a saida real do `netci`, copiada sem edicao por
`tools/gerar_exemplo.py`. Por isso o exemplo serve como prova do
comportamento em vez de descricao dele: se o pipeline mudar e este
arquivo nao acompanhar, o `git diff --exit-code` do CI falha.

Para reproduzir localmente:

```powershell
python tools/gerar_exemplo.py
```

## Reprovado no estagio de sintaxe

Comando: `python -m netci validar dados/candidatos/switch-ruins-sintaxe.cfg --golden dados/golden/switch-core.cfg`

Saida (codigo de saida `1`):

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

Um `trun` onde se queria `trunk`. Os tres estagios seguintes aparecem marcados como nao executados: o pipeline parou, e o relatorio diz qual foi o motivo da parada. Uma estagio que passou e um estagio que nao rodou sao coisas diferentes, e a diferenca esta escrita no proprio relatorio.

## Reprovado no estagio de regras de negocio

Comando: `python -m netci validar dados/candidatos/switch-ruins-regras.cfg --golden dados/golden/switch-core.cfg`

Saida (codigo de saida `1`):

```
========================================================================
CI DE REDE - dados/candidatos/switch-ruins-regras.cfg
========================================================================

ESTAGIOS
  sintaxe    0 erro(s), 0 aviso(s)
  regras     3 erro(s), 0 aviso(s)
  golden     nao rodou (estagio anterior reprovou)
  testes     nao rodou (nao solicitado: use --origem e --destino)

INTERROMPIDO EM: regras
Os estagios seguintes dependem deste e nao foram executados.
Corrigir o achado acima e rodar de novo.

ACHADOS
  [ERRO ] VLAN_DUPLICADA
  onde: linha 26
  o que: VLAN 10 declarada duas vezes
  como corrigir: a primeira declaracao esta na linha 24

  [ERRO ] ACL_SEM_DENY
  onde: linha 43
  o que: ACL 100 nao termina em 'deny ip any any'; o padrao implicito e permitir
  como corrigir: adicione 'access-list 100 deny ip any any' como ultima entrada

  [ERRO ] ROTA_PADRAO_DUPLICADA
  onde: linha 47
  o que: rota padrao declarada mais de uma vez; o equipamento obedece a ultima
  como corrigir: a primeira declaracao esta na linha 46; apague a que sobrar

========================================================================
RESULTADO: REPROVADO
3 erro(s) bloqueiam o merge. O candidato nao pode ser aplicado.
```

Este arquivo passa na sintaxe e reprova em negocio: VLAN duplicada, rota padrao duplicada e ACL sem o `deny` final. Sao tres problemas independentes, e os tres aparecem com linha e com a sugestao de correcao.

## Aprovado com avisos

Comando: `python -m netci validar dados/candidatos/switch-ok-2.cfg --golden dados/golden/switch-core.cfg`

Saida (codigo de saida `0`):

```
========================================================================
CI DE REDE - dados/candidatos/switch-ok-2.cfg
========================================================================

ESTAGIOS
  sintaxe    0 erro(s), 0 aviso(s)
  regras     0 erro(s), 0 aviso(s)
  golden     0 erro(s), 1 aviso(s)
  testes     nao rodou (nao solicitado: use --origem e --destino)

ACHADOS
  [AVISO] VLAN_NOVA
  onde: linha 21
  o que: VLAN 50 declarada no candidato mas ausente na referencia
  como corrigir: VLAN nova nao bloqueia; o revisor precisa saber que ela existe

========================================================================
RESULTADO: APROVADO COM AVISOS
Todos os estagios rodaram. O candidato pode seguir para o merge.
```

A VLAN 50 nao existe na referencia. Isso e aviso e nao erro: uma VLAN nova e mudanca legitima, e o estagio nao e dono da decisao de aceita-la. O merge passa, e o revisor ve que ela existe.

## Teste de conectividade, quando pedido

Comando: `python -m netci validar dados/candidatos/switch-ok-1.cfg --golden dados/golden/switch-core.cfg --origem 192.168.30.2 --destino 192.168.30.9`

Saida (codigo de saida `1`):

```
========================================================================
CI DE REDE - dados/candidatos/switch-ok-1.cfg
========================================================================

ESTAGIOS
  sintaxe    0 erro(s), 0 aviso(s)
  regras     0 erro(s), 0 aviso(s)
  golden     0 erro(s), 0 aviso(s)
  testes     1 erro(s), 0 aviso(s)

ACHADOS
  [ERRO ] TESTE_BLOQUEADO_POR_ACL
  onde: linha 32
  o que: caminho de 192.168.30.2 para 192.168.30.9 existe mas a ACL nega tudo: deny ip any any
  como corrigir: a negacao implicita fecha o caminho antes do destino

========================================================================
RESULTADO: REPROVADO
1 erro(s) bloqueiam o merge. O candidato nao pode ser aplicado.
```

O caminho entre os dois enderecos existe, porque os dois estao na subnet que a interface Vlan30 declara. A ACL numerada do arquivo termina em `deny ip any any`, e essa negacao implicita fecha o caminho. O estagio prova logica de enderecamento e nada alem disso.

## O pipeline inteiro de uma vez

Comando: `python -m netci pipeline dados/candidatos --golden dados/golden/switch-core.cfg`

Saida (codigo de saida `1`):

```
========================================================================
PIPELINE DE 5 CANDIDATO(S)
========================================================================
APROVADO             0 erro(s)  0 aviso(s)  switch-ok-1.cfg
APROVADO COM AVISOS  0 erro(s)  1 aviso(s)  switch-ok-2.cfg
APROVADO             0 erro(s)  0 aviso(s)  switch-ok-3.cfg
REPROVADO            3 erro(s)  0 aviso(s)  switch-ruins-regras.cfg
REPROVADO            1 erro(s)  0 aviso(s)  switch-ruins-sintaxe.cfg

========================================================================
CI DE REDE - dados\candidatos\switch-ruins-regras.cfg
========================================================================

ESTAGIOS
  sintaxe    0 erro(s), 0 aviso(s)
  regras     3 erro(s), 0 aviso(s)
  golden     nao rodou (estagio anterior reprovou)
  testes     nao rodou (nao solicitado: use --origem e --destino)

INTERROMPIDO EM: regras
Os estagios seguintes dependem deste e nao foram executados.
Corrigir o achado acima e rodar de novo.

ACHADOS
  [ERRO ] VLAN_DUPLICADA
  onde: linha 26
  o que: VLAN 10 declarada duas vezes
  como corrigir: a primeira declaracao esta na linha 24

  [ERRO ] ACL_SEM_DENY
  onde: linha 43
  o que: ACL 100 nao termina em 'deny ip any any'; o padrao implicito e permitir
  como corrigir: adicione 'access-list 100 deny ip any any' como ultima entrada

  [ERRO ] ROTA_PADRAO_DUPLICADA
  onde: linha 47
  o que: rota padrao declarada mais de uma vez; o equipamento obedece a ultima
  como corrigir: a primeira declaracao esta na linha 46; apague a que sobrar

========================================================================
RESULTADO: REPROVADO
3 erro(s) bloqueiam o merge. O candidato nao pode ser aplicado.

========================================================================
CI DE REDE - dados\candidatos\switch-ruins-sintaxe.cfg
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

========================================================================
3 aprovado(s), 2 reprovado(s)
```

A leitura que interessa vem primeiro: o veredito de cada candidato lado a lado, e so depois o detalhe de quem foi reprovado. Quem aprovado aparece em uma linha porque nao ha nada a ler sobre ele.

## As regras do pipeline

Comando: `python -m netci regras`

Saida (codigo de saida `0`):

```

sintaxe:
  COMANDO_DESCONHECIDO         primeira palavra fora do vocabulario
  PARAMETRO_INVALIDO           argumento numerico que nao e numero
  VALOR_INVALIDO               valor fora do conjunto permitido
  INTERFACE_DUPLICADA          mesma interface declarada duas vezes
  INTERFACE_VAZIA              bloco interface sem subcomando
  SUBCOMANDO_DESCONHECIDO      linha de interface nao reconhecida
  SEM_HOSTNAME                 arquivo sem comando hostname

regras:
  VLAN_DUPLICADA               mesma VLAN declarada duas vezes
  ROTA_PADRAO_DUPLICADA        mais de uma rota padrao para 0.0.0.0
  ROTA_PARA_SI                 proximo salto da rota e endereco de interface do proprio arquivo
  ACL_SEM_DENY                 ACL numerada que nao termina em 'deny ip any any'
  SEM_FILTRO_DE_ENTRADA        nenhum access-list no arquivo
  VLAN_SEM_INTERFACE           VLAN declarada que nenhuma interface referencia
  SEM_MASCARA                  ip address sem mascara

golden:
  SEM_ENABLE_SECRET            candidato sem enable secret
  SEM_LINE_VTY                 candidato sem bloco line vty
  VTY_SEM_PASSWORD             line vty sem password em nenhuma das linhas
  ACL_SEM_DENY_ANY             ACL numerada que nao termina em deny ip any any
  SEM_SPANNING_TREE            candidato sem spanning-tree mode
  SEM_INTERFACE_TRUNK          nenhuma interface em modo trunk
  VLAN_NOVA                    VLAN no candidato que a referencia nao declara

testes:
  TESTE_SEM_CAMINHO            nao ha rota nem subnet compartilhada
  TESTE_BLOQUEADO_POR_ACL      o caminho existe mas uma ACL nega
  TESTE_OK                     o caminho existe e nenhuma ACL nega

24 regra(s) no pipeline
```

Todos os codigos de regra, por estagio. O codigo e estavel de proposito: CI precisa ser compativel, e um alerta que muda de nome a cada versao faz o historico do pipeline deixar de fazer sentido.

## Como ler um relatorio vermelho

O relatorio traz quatro coisas por achado: a linha, o codigo da regra, o que aconteceu e como corrigir. A correcao sugerida vem das regras e nao do relatorio, e por isso ela e acionavel.

Os achados vem em ordem de gravidade, e nao de linha: quem tem quarenta avisos e um erro precisa ver o erro primeiro.

Um estagio que aparece como `nao rodou` nao passou. Ele tem duas causas possiveis, e o relatorio distingue as duas: o estagio anterior reprovou, ou o estagio nao foi pedido. A segunda aparece quando o teste de conectividade nao tem `--origem` e `--destino`, e e o caso em que o pipelineApproved e o teste de conectividade simplesmente nao aconteceu.
