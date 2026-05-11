# Plano de testes beta Tenfy

Este documento orienta a homologacao da versao beta/MVP do Tenfy. O objetivo e ajudar os testadores a validar o que ja existe no produto, reportar bugs com clareza e separar sugestoes futuras de problemas reais.

## Objetivo da homologacao

Validar os fluxos principais do Tenfy antes de ampliar o acesso:

- criar conta e acessar o app;
- configurar perfil esportivo;
- cadastrar dependentes quando o usuario for pai/responsavel;
- consultar torneios compativeis;
- salvar torneios na agenda/inscricoes;
- acompanhar resultados;
- recuperar senha;
- excluir conta ou solicitar dados quando necessario.

## Regra de ouro para testadores

Durante a homologacao, reporte bugs do que ja existe. Sugestoes de novas funcionalidades sao bem-vindas, mas devem ir na secao "Sugestao futura" e nao devem bloquear o teste.

Exemplo de bug:

> Ao selecionar o perfil do Leonardo, a tela de torneios ainda mostra dados da Kamille.

Exemplo de sugestao futura:

> Seria legal ter chat entre pais e treinadores.

## Perfis de teste

Use os tipos abaixo quando possivel:

- Jogador individual: usuario que cria e usa o proprio perfil esportivo.
- Pai/responsavel: usuario que gerencia dependentes.
- Dependente: filho/atleta cadastrado pelo responsavel, com login proprio.
- Tester: plano beta com funcionalidades liberadas para homologacao.
- Usuario sem perfil: usuario logado que ainda nao configurou perfil esportivo.

## Severidade dos problemas

Classifique cada relato:

- Bloqueante: impede login, cadastro, uso basico ou acesso ao app.
- Alto: fluxo importante quebra, como criar dependente, selecionar perfil ou ver torneios compativeis.
- Medio: erro atrapalha, mas existe contorno.
- Baixo: texto, visual, alinhamento, mensagem confusa ou pequeno detalhe.
- Sugestao futura: ideia nova, melhoria desejada ou funcionalidade fora do MVP.

## Como reportar um bug

Copie e preencha:

```text
Titulo:

Severidade:
Bloqueante / Alto / Medio / Baixo / Sugestao futura

Dispositivo:
Ex: Android Samsung A54, iPhone 13, navegador Chrome

Sistema:
Ex: Android 14, iOS 17, Windows 11

Conta usada:
Ex: jogador, responsavel, dependente, tester

Tela:
Ex: Login, Perfil, Torneios, Agenda, Resultados

Passos para reproduzir:
1.
2.
3.

Resultado esperado:

Resultado obtido:

Print ou video:
Anexar se possivel.
```

## Prompt para ajudar com IA

Se o relato estiver confuso, o testador pode usar:

```text
Transforme este relato em um bug claro para o time do Tenfy.
Nao invente funcionalidades novas.
Separe em: titulo, severidade sugerida, tela, passos para reproduzir, resultado esperado, resultado obtido e evidencias.

Relato:
[cole aqui o que aconteceu]
```

## O que nao testar agora como obrigatorio

Estes itens podem virar sugestao futura, mas nao devem bloquear a homologacao:

- inscricao oficial em torneio dentro do Tenfy;
- pagamento real em producao;
- chat interno;
- ranking completo e oficial de todas as fontes;
- notificacoes avancadas multicanal;
- automacoes administrativas complexas;
- layout perfeito para tablet;
- funcionalidades de treinador que ainda nao estejam claramente liberadas.

## Checklist rapido

Use esta lista para uma rodada curta de teste:

- Criar conta tester.
- Confirmar e-mail, se solicitado.
- Ver aviso beta/MVP.
- Criar perfil esportivo como jogador.
- Criar conta como pai/responsavel.
- Cadastrar dependente com perfil esportivo completo.
- Fazer login como dependente.
- Selecionar perfil/dependente ativo.
- Ver torneios compativeis do perfil selecionado.
- Salvar torneio na agenda.
- Marcar torneio como inscrito.
- Ver agenda/inscricoes.
- Ver resultados.
- Recuperar senha.
- Excluir conta ou localizar a opcao de exclusao.

## Cenarios detalhados

### 1. Cadastro de usuario tester

Objetivo: validar criacao de conta no plano beta.

Pre-condicoes:

- app instalado;
- e-mail ainda nao cadastrado.

Passos:

1. Abrir o app.
2. Tocar em criar conta.
3. Selecionar o plano tester, se houver escolha de plano.
4. Preencher nome, e-mail e senha.
5. Finalizar cadastro.

Resultado esperado:

- conta criada com sucesso;
- usuario entra no app ou segue para verificacao de e-mail;
- nenhum plano pago e iniciado;
- aviso beta/MVP aparece no primeiro acesso.

Reportar se:

- cadastro falhar sem mensagem clara;
- plano errado for selecionado;
- checkout/pagamento abrir por engano;
- aviso beta nao aparecer.

### 2. Login

Objetivo: validar acesso de usuario existente.

Passos:

1. Abrir o app.
2. Informar e-mail e senha.
3. Entrar.

Resultado esperado:

- login realizado;
- app abre na Home;
- dados do usuario correto aparecem;
- aviso beta aparece se ainda nao foi confirmado.

Reportar se:

- login valido falhar;
- app mostrar dados de outro usuario;
- tela travar carregando.

### 3. Recuperacao de senha

Objetivo: validar envio e uso do e-mail de recuperacao.

Passos:

1. Na tela de login, tocar em recuperar senha.
2. Informar e-mail cadastrado.
3. Enviar.
4. Abrir e-mail recebido.
5. Redefinir senha.
6. Fazer login com a nova senha.

Resultado esperado:

- usuario recebe e-mail;
- link abre pagina com identidade Tenfy;
- nova senha funciona.

Reportar se:

- e-mail nao chegar;
- link abrir tela com marca antiga;
- senha redefinida nao funcionar.

### 4. Perfil esportivo individual

Objetivo: validar criacao e edicao do perfil de jogador.

Passos:

1. Entrar como jogador.
2. Abrir Perfil.
3. Criar ou editar perfil esportivo.
4. Preencher ano/data de nascimento, genero, cidade/UF, estados onde aceita jogar, nivel e classe.
5. Salvar.

Resultado esperado:

- perfil e salvo;
- idade esportiva e calculada corretamente;
- Home/Torneios passam a usar esse perfil.

Reportar se:

- perfil nao salvar;
- idade esportiva estiver errada;
- app continuar dizendo "perfil nao configurado".

### 5. Pai/responsavel sem perfil proprio

Objetivo: validar responsavel que gerencia dependentes sem ser jogador.

Passos:

1. Criar ou entrar como responsavel.
2. No primeiro fluxo, selecionar que e pai/responsavel.
3. Concluir sem criar perfil esportivo proprio.
4. Abrir Home.

Resultado esperado:

- app nao deve atribuir idade esportiva de dependente ao responsavel;
- app deve orientar a cadastrar ou selecionar dependente;
- "Compativeis com voce" so deve aparecer quando houver perfil ativo selecionado.

Reportar se:

- Home mostrar idade de um dependente como se fosse do responsavel;
- app exigir perfil proprio do responsavel indevidamente.

### 6. Cadastro de dependente

Objetivo: validar criacao de dependente com conta e perfil esportivo.

Pre-condicoes:

- usuario responsavel em plano tester ou familia.

Passos:

1. Abrir Perfil.
2. Ir em "Meus dependentes - Perfil esportivo".
3. Tocar em Novo.
4. Preencher nome, e-mail e senha do dependente.
5. Preencher perfil esportivo completo do dependente.
6. Salvar.

Resultado esperado:

- dependente e criado;
- perfil esportivo e criado junto;
- card mostra nome, e-mail e dados principais;
- senha nao aparece depois de salvar;
- dependente pode fazer login.

Reportar se:

- sistema permitir dependente sem perfil esportivo;
- responsavel sem permissao conseguir criar dependente;
- limite de dependentes nao for respeitado;
- dependente nao conseguir logar.

### 7. Selecionar dependente para compatibilidade

Objetivo: validar troca de perfil ativo.

Passos:

1. Entrar como responsavel com pelo menos dois dependentes.
2. Selecionar Leonardo como perfil ativo.
3. Abrir Torneios/Home.
4. Anotar torneios compativeis.
5. Selecionar Kamille como perfil ativo.
6. Abrir Torneios/Home novamente.

Resultado esperado:

- app mostra claramente qual perfil esta ativo;
- torneios compativeis mudam conforme o perfil;
- dados nao se misturam entre dependentes.

Reportar se:

- seletor nao existir;
- app continuar usando o perfil anterior;
- Home/Torneios misturarem dados.

### 8. Listagem e filtros de torneios

Objetivo: validar busca de torneios.

Passos:

1. Abrir Torneios.
2. Usar filtros de federacao/status/localidade, se disponiveis.
3. Abrir um torneio.
4. Voltar para a lista.

Resultado esperado:

- lista carrega;
- filtros funcionam;
- detalhe do torneio abre;
- datas, cidade, categoria, preco e fonte aparecem quando disponiveis.

Reportar se:

- lista nao carregar;
- filtro quebrar;
- detalhe mostrar dados incoerentes.

### 9. Detalhe do torneio e agenda

Objetivo: validar acompanhamento de torneio.

Passos:

1. Abrir um torneio.
2. Tocar em acompanhar/salvar na agenda.
3. Ir para Agenda.
4. Alterar status para inscrito, se disponivel.

Resultado esperado:

- torneio aparece na agenda;
- status e salvo;
- se houver perfil ativo, item fica associado ao perfil correto.

Reportar se:

- item nao aparecer na agenda;
- status nao persistir;
- item aparecer no dependente errado.

### 10. Agenda/inscricoes por dependente

Objetivo: validar agrupamento por dependente.

Passos:

1. Entrar como responsavel.
2. Ter pelo menos dois dependentes.
3. Salvar ou marcar torneios para cada dependente.
4. Abrir Agenda/Inscricoes.

Resultado esperado:

- itens aparecem separados por dependente;
- cada grupo mostra nome do dependente;
- nenhum item de um dependente aparece no grupo de outro.

Reportar se:

- Agenda nao trouxer dependentes;
- itens ficarem todos misturados;
- dados de um dependente aparecerem para outro.

### 11. Resultados

Objetivo: validar acompanhamento de resultados.

Passos:

1. Abrir Resultados.
2. Ver itens inscritos ou com resultado.
3. Se permitido, registrar/editar resultado.

Resultado esperado:

- jogador individual ve apenas seus resultados;
- responsavel ve resultados agrupados por dependente;
- dependente logado ve apenas seus proprios resultados.

Reportar se:

- resultados nao carregarem;
- dados de outro usuario aparecerem;
- agrupamento por dependente falhar.

### 12. Login como dependente

Objetivo: validar isolamento do dependente.

Passos:

1. Sair da conta do responsavel.
2. Entrar com e-mail e senha do dependente.
3. Abrir Perfil, Torneios, Agenda e Resultados.

Resultado esperado:

- dependente ve apenas o proprio perfil;
- dependente nao gerencia outros dependentes;
- dados do responsavel nao aparecem indevidamente.

Reportar se:

- dependente conseguir gerenciar perfis de terceiros;
- dados do responsavel ou irmaos aparecerem.

### 13. Exclusao de conta e privacidade

Objetivo: validar acesso a recursos LGPD.

Passos:

1. Abrir Perfil.
2. Localizar secao de privacidade.
3. Verificar opcao de exportar dados, se disponivel.
4. Verificar opcao "Excluir minha conta".

Resultado esperado:

- opcoes existem;
- mensagens deixam claro o impacto;
- exclusao exige confirmacao.

Reportar se:

- opcao nao existir;
- exclusao ocorrer sem confirmacao;
- app travar apos excluir conta.

## Checklist para rodada oficial

Cada testador deve tentar completar:

```text
[ ] Criar conta tester
[ ] Confirmar e-mail, se aplicavel
[ ] Ver aviso beta/MVP
[ ] Criar perfil individual ou seguir como responsavel
[ ] Cadastrar dependente com perfil esportivo completo
[ ] Fazer login como dependente
[ ] Selecionar perfil ativo no responsavel
[ ] Ver torneios compativeis do perfil selecionado
[ ] Salvar torneio na agenda
[ ] Marcar torneio como inscrito
[ ] Ver Agenda/Inscricoes
[ ] Ver Resultados
[ ] Recuperar senha
[ ] Localizar exclusao de conta
[ ] Reportar bugs usando o modelo
```

## Como consolidar feedback

Ao receber relatos:

1. Classifique como bug ou sugestao futura.
2. Agrupe bugs duplicados.
3. Priorize bloqueantes e altos.
4. So transforme sugestao em tarefa depois da rodada de homologacao.
5. Evite alterar escopo durante a rodada sem decisao explicita.

