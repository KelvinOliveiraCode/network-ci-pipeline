# O que bloquear em CI

Este documento explica o raciocínio por trás das regras que o pipeline da
rede trata como erro e que deixam para o revisor. Não é uma lista de
regras. Uma lista muda toda semana; o raciocínio dura.

## O problema real não é bloquear demais

Há duas formas ruins de entender um CI de configuração: achar que o
problema é ele bloquear muito, ou achar que o problema é ele bloquear
pouco. A primeira é ingenuidade; a segunda é o que acontece na prática.

Um CI que nunca bloqueia não é permissivo. É inútil. Ele desenha em
vermelho no que estava fechado, mas o merge continua. Documenta em vez de
proteger. Uma vez que o vermelho não impede nada, ele vira decoração do
relatório, e a função original de CI desaparece: a configuração passa a
ser aprovada por fé no revisor, não por verificação.

Do outro lado, um CI que bloqueia tudo treina o time a clicar em "aprovar
mesmo assim". Cada falso positivo é um pequeno preço pago. O custo de um
falso positivo não é o tempo de corrigir o achado, que é rápido. É o tempo de perder o hábito
de ler. Quem aprende que o vermelho aparece sem motivo, deixa de ler o
vermelho quando aparece com motivo; então o erro real passa despercebido
exatamente porque o vermelho virou ruído.

O custo do bloqueio errado não é corrigir; é desmoralizar a leitura.

## O critério de decisão

Um critério precisa ser concreto e defensável, senão vira opinião de
quem está de plantão. O que escolho usar é: bloqueia o que derruba serviço,
o que abre acesso que estava fechado, ou o que é impossível recuperar sem
ir no equipamento.

Derruba serviço é claro. Um erro de sintaxe invalida a configuração inteira;
uma VLAN duplicada cria comportamento indeterminado; um cabeamento lógico
errado fecha o caminho. Isso o pipeline para, porque não dá para chegar lá
e arrancar.

Abre acesso que estava fechado é o mais perigoso, porque o dano é
silencioso. Um erro de ACL que deixa uma porta liberada a mais não quebra
nada no teste — pelo contrário, o teste até aprova, já que o caminho está
aberto. Só quem sabe o que era fechado descobre. Bloquear isso no CI é
proteger quem não vai estar no equipamento quando o incidente chegar.

Impossível recuperar sem ir no equipamento é uma fronteira menos óbvia.
Configuração escrita errada, no computador de quem configura, é fácil de
consertar. Configuração aplicada em produção, no equipamento real, exige
janela, acesso físico ou remoto, e impacto no tráfego. O CI tenta
adiantar esse tipo de decisão para o momento de menor custo, que é antes
do merge, não depois da falha.

Não bloqueia o que é desvio de estilo, o que é recomendação, e o que o
revisor pode julgar em dez segundos. Um nome de VLAN fora da convenção, um comentário fora do padrão, uma ordem
de comandos alternativa que funciona igual — o revisor vê e decide, sem
parar o merge. Isso não protege ninguém; só ocupa a fila.

Por que a separação entre erro e aviso precisa existir no código e não só
na documentação? Porque documentação é lê-se, e a decisão de bloquear é
executada. Um estagio que retorna um achado genérico e deixa que o relatorio invente
a severidade no final tem uma falha simples: separa o achado da intenção.
Quem escreveu a regra sabia o que era grave; se essa intenção não estiver
declarada junto com o achado, o relatorio vai classificar de outra forma
na próxima vez que alguém mexer nele. Cada regra de cada estagio declara a
sua severidade no momento do achado, para que erro e aviso sigam juntos da
origem até o merge. A distinção é sobre
quem age: erro bloqueia o merge porque a configuração está errada; aviso
não bloqueia porque é um desvio que o revisor precisa ver e decidir.

## O caso do golden config

Comparar a configuração candidata com uma configuração de referência é
tentador e, se for feito como igualdade estrita, está errado.

A referência é uma foto do que está OK em um dia. Toda mudança legítima —
uma VLAN nova, uma interface que foi desativada, um comentário atualizado,
um parâmetro que virou prática — passa a ser reprovada, porque não está na
foto. O resultado não é configuração mais segura; é uma lista de
diferenças contra a linha de base, que o time começa a chamar de "ruído
do golden config" e passa a ignorar. A mesma dinâmica do parágrafo
anterior: o vermelho aparece sem motivo, e a leitura acaba.

A comparação tem que ser sobre o que não pode faltar, não sobre a lista
completa. Pergunta correta: a configuração candidata tem tudo o que o
padrão exige? Pergunta errada: a configuração candidata é igual à
referência?

Isso muda o que o estágio faz. Em vez de comparar byte a byte contra o
template, o golden config verifica presença e não-presença: os itens
obrigatórios existem, os itens proibidos não, e cada bloco obrigatório tem
os campos mínimos. O resto é livre.

O laboratório deste projeto é o exemplo. Uma VLAN nova não é erro. Uma
interface a menos não é erro. Ambos são mudanças legítimas que a igualdade
estrita condenaria. O que é erro aqui é o bloco de interface incompleto,
o comando proibido na configuração, ou a referência a algo que não existe
e que, se o equipamento tentasse aplicar, iria falhar.

Aproveita que o pipeline para no primeiro estágio que falha: sintaxe antes
de regra de negócio, regra de negócio antes do golden config. Um erro de
sintaxe muda a leitura do que vem depois, então os achados seguintes seriam
consequência, não causa. Parar no primeiro não é rigidez; é economia de
leitura. A única exceção é o relatório, que sempre roda, porque é ele que
diz o que aconteceu.

## Onde o simulado substitui o equipamento real

A honestidade aqui é parte do valor do pipeline, não um defeito dele.

Este pipeline testa endereçamento, rota e ACL. Ele verifica se os
endereços estão dentro do plano, se o caminho entre as redes existe, e se
as regras de acesso correspondem ao que o documento de segurança pede.
Isso é uma parte útil e frequentemente negligenciada da configuração.

Ele não testa se o equipamento sobe. Não testa se o hardware daquela linha
suporta a configuração. Não testa performance, nem como o tráfego real se
comporta sob carga, nem se há conflitos com configurações aplicadas em
outro lugar. Ele prova o que o modelo dele consegue provar: lógica de
configuração, não realidade de operação.

Por que ainda assim vale a pena? Porque o erro de configuração é
sistemático e repetitivo. Um mesmo tipo de erro aparece em cada mudança,
cada uma exigindo atenção humana e cada uma correndo o risco de escapar.
Um simulado pega os erros recorrentes e os impede de chegar ao equipamento. O que ele não cobre continua a ser coberto pelo revisor e pelo
teste em produção, que existem de propósito.

O risco a nomear com clareza: dar confiança cega a um simulado que só
prova o que ele sabe provar. Se a configuração passa no teste, significa
que está coerente com o modelo do teste — não que vai funcionar no
equipamento. A confiança do simulado é condicional: a certa para a parte
que ele cobre, e falta de cuidado usá-lo como cobertura do resto.

## Quando relaxar uma regra é a coisa certa

Avaliar se uma regra deve continuar bloqueando não é só no começo. É um
exercício contínuo, porque a regra e o ambiente mudam em ritmos diferentes.

Se uma regra disparou diversas vezes e nenhuma vez foi problema real — se
o achado se mostrou consistentemente inofensivo, ou se virou um desvio
consensual que o time adota de propósito — ela não está mais servindo ao
critério de bloquear o que derruba serviço, abre acesso ou é irreversível
naquele momento. O correto é rebaixá-la de erro para aviso ou removê-la.

Uma regra que ninguém respeita é dívida técnica com custo de leitura: ocupa
o tempo de quem lê o relatório hoje e dilui o impacto dos erros que
realmente importam. Apagar uma regra desatualizada é manutenção, não
rendição.
