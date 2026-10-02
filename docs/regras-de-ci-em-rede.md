# Regras de CI em rede

## Um pipeline que nunca reprova

Documentar um pipeline de CI só para descrever o que ele faz não serve. Um pipeline verde que nunca fica vermelho é um relatório que ninguém lê, e um relatório que ninguém lê é um relatório que não existe. Esta documentação existe porque o pipeline aqui reprova de propósito: cada um dos seus quatro estágios de verificação responde a uma pergunta diferente sobre a configuração, e cada um pode barrar o merge.

Este projeto, netci, é um laboratório fictício. A entrada são arquivos `.cfg` com configuração simulada de switch; não há equipamento conectado e nada nesta execução toca na rede. As regras foram escritas para esse ambiente e valem apenas para ele. O importante não é o que uma regra faz em particular, mas como as regras se dividem em perguntas, códigos estáveis e duas severidades — porque é essa divisão que o relatório consome e é ela que o time precisa ler.

## Os cinco estágios

O pipeline executa quatro etapas de verificação e, depois, produz o relatório. A ordem importa: é a mesma ordem que a regra de parada consulta.

**1. Sintaxe — "esta configuração faz sentido como texto?"** Não sabe se a VLAN 10 é legítima, se a ACL é necessária ou se o resultado é o esperado. Sabe se `switchport mode trun` é uma palavra reconhecível, se um argumento numérico virou texto e se um bloco de interface foi fechado. Exemplo real do laboratório: `vlan 5000` gera o achado VALOR_INVALIDO, erro, na linha da declaração: "VLAN 5000 fora de 1..4094". Sintaxe é o que impede que os estágios seguintes leiam um arquivo que não existe.

O que o estágio NÃO responde: nada sobre o funcionamento da rede, sobre o estado anterior ou sobre intenção de quem escreveu.

**2. Regras de negócio — "faria sentido essa configuração no laboratório?"** A sintaxe já passou; aqui não há checagem de grafia, só semântica. Confere a VLAN declarada duas vezes, rota padrão duplicada, próximo salto apontando para um endereço próprio do arquivo, ACL numerada sem `deny ip any any` no final e `ip address` sem máscara. Exemplo real: `access-list 10` cujas entradas terminam em `permit tcp any any host 192.168.10.10 eq 80` gera ACL_SEM_DENY: "ACL 10 não termina em 'deny ip any any'; o padrão implícito é permitir". ACL numerada nega nada por padrão, então tudo que não foi listado passa. Esse achado para o merge.

O que o estágio NÃO responde: se o equipamento vai aceitar a regra, se a ACL é a que o revisor queria, ou se o comportamento está correto em produção.

**3. Golden config — "esta configuração continua estruturalmente completa?"** Compara o candidato contra a configuração de referência, o estado conhecido como bom, mas a comparação não é igualdade estrita: se fosse, qualquer mudança legítima — uma VLAN nova, uma interface a mais, uma a menos — reprovaria e o time aprenderia a ignorar o CI. Confere o que não pode faltar em nenhuma configuração saudável: enable secret, bloco `line vty` com password, ACL numerada terminando em `deny ip any any`, `spanning-tree mode` e pelo menos uma interface em trunk. Exemplo real de erro: candidato sem `enable secret` gera SEM_ENABLE_SECRET, erro: "sem isso não há modo privilegiado; o equipamento fica administrável só por console físico". Exemplo real de aviso: o candidato declara VLAN 50 e a referência não a declara, gerando VLAN_NOVA, aviso — passa, o revisor precisa saber que ela existe.

O que o estágio NÃO responde: perda de configuração opcional (VLAN que só existe na referência não aparece), nem desvios de configuração que a referência também não tem.

**4. Teste simulado — "esse caminho existe?"** Único estágio que responde sobre existência de caminho, e a resposta é sobre lógica de endereçamento, não sobre a rede. Nada abre socket, nenhum nome é resolvido, nada fala com o switch; é aritmética de endereço IPv4. Tem exatamente três saídas: TESTE_OK, TESTE_SEM_CAMINHO e TESTE_BLOQUEADO_POR_ACL. Só o `deny ip any any` fecha o caminho; um `deny` específico, como `deny tcp any any eq 23`, não fecha tráfego de outros destinos e seria injusto tratar como bloqueio. Exemplo real: origem 192.168.10.10, destino 192.168.30.2, sem subnet compartilhada e sem rota gera TESTE_SEM_CAMINHO, erro: "sem caminho de 192.168.10.10 para 192.168.30.2: nenhuma subnet compartilhada e nenhuma rota". Os alvos que o laboratório nomeia por convenção são gerencia (192.168.30.2), servidor (192.168.20.10), estacao (192.168.10.10) e visitante (192.168.40.10).

O que o estágio NÃO prova: que a configuração seja aceita pelo equipamento, que o hardware suporte o pedido ou que exista performance.

**5. Relatório — não é verificação, é a soma.** Conhece todos os estágios, herda seus códigos e severidades e imprime um achado por linha. Não produz achado próprio, por isso não entra na cadeia de execução e sempre roda.

## As duas severidades

Dois níveis, e a distinção é sobre quem age. ERRO bloqueia o merge: a configuração está errada. AVISO não bloqueia; é um desvio que o revisor precisa ver e decidir. Um pipeline que bloqueia por tudo treina o time a ignorar o vermelho; um pipeline que nunca bloqueia não é CI. A separação não é textual: cada regra declara sua severidade no código e o relatório só herda. Por isso uma regra de negócio e uma regra de golden podem falar do mesmo defeito e ter severidades diferentes. A classe Achado expõe `bloqueia`, além de `erros` e `avisos`, que o relatório e a regra de parada consomem.

Exemplos do laboratório:
- Candidato com VLAN 50 declarada e a referência não a declara => VLAN_NOVA, aviso. A comparação golden ignora o que só existe na referência; falta de configuração opcional é decisão do revisor, não do CI. O achado aparece no relatório e o merge passa.
- Candidato com ACL 10 terminando em `permit tcp any any` => ACL_SEM_DENY, erro. O padrão implícito de ACL é permitir; tudo não listado passa. Esse achado para o pipeline.

A mesma ideia com severidades opostas aparece em dois códigos: ACL_SEM_DENY (negócio) e ACL_SEM_DENY_ANY (golden) são erro nos dois, enquanto VLAN_NOVA é aviso exclusivo de golden.

## A regra de parada

O pipeline roda os estágios na ordem sintaxe, regras, golden, testes. Para no primeiro estágio que acha algum ERRO. A tentação é rodar tudo e juntar os erros, achando que um relatório com sete problemas é mais útil que um com um. É o oposto: erro de sintaxe muda a leitura de tudo que vem depois. Um `trun` que ninguém reconhece faz a regra de negócio não encontrar a porta access que deveria estar ali, e o relatório passa a listar como problema de negócio algo que é consequência do problema de sintaxe. Quem lê o relatório corrige o primeiro erro, roda de novo, só então vê os outros, e chega ao mesmo lugar com mais esforço e menos informação sobre a causa.

O estágio de regras de negócio roda mesmo quando o de sintaxe reprova. Parece contradizer o parágrafo acima, mas não contradiz: as duas coisas são erros concorrentes, não dependentes. A VLAN duplicada existe independentemente de qualquer `trun` torto no arquivo. Os dois estão no arquivo, os dois precisam ser corrigidos e corrigir um primeiro faz o outro continuar lá. A linha que separa as duas situações é simples: o segundo achado existe independentemente do primeiro? Se sim, vale rodar. Se não, o segundo é consequência e o pipeline para.

## O que fica de fora

Lista honesta do que este pipeline não verifica. Nada aqui se pretende completo — a honestidade sobre os limites é parte do valor, não um defeito.

- Performance: não mede CPU, memória, throughput, latência, nem tabelas de ARP ou MAC.
- Hardware: não sabe se o switch físico suporta o pedido, nem quantas interfaces ou VLANs existem fisicamente.
- Compatibilidade de versão: não verifica se os comandos existem naquela versão do sistema do switch; um arquivo pode passar aqui e ser rejeitado no primeiro commit do equipamento.
- Estado real do equipamento: nada abre socket, não resolve nome, não fala com o switch; não há dados de runtime.
- Estado da rede: não sabe se as VLANs já existem no domínio, se os uplinks estão up ou se há loops.
- Intenção do revisor: não distingue uma ACL escrita por acidente de uma ACL escrita por política de segurança.
- O teste de conectividade prova apenas lógica de endereçamento: que, segundo a configuração escrita, o caminho existe. Se a VLAN 20 está isolada e sem rota para a VLAN 10, o pacote não chega — e isso não depende de o equipamento estar ligado.

Para ler o raciocínio por trás do que bloqueia e do que fica para o revisor, veja `docs/o-que-bloquear-em-ci.md`. O pipeline reduz risco, não o elimina. Ele é um filtro que pergunta se o plano está autoconsistente; não uma garantia de que a rede vai funcionar.
