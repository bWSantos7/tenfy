# CLAUDE.md — Instruções obrigatórias para IA no projeto Tennis Hub

Este arquivo deve ser lido obrigatoriamente antes de qualquer alteração no projeto.

O objetivo deste documento é dar contexto de produto, escopo contratual do MVP, regras de arquitetura, padrões de segurança e diretrizes de desenvolvimento para qualquer IA ou desenvolvedor que atue no código do Tennis Hub.

---

## 1. Visão geral do projeto

O Tennis Hub é uma plataforma digital para jogadores de tênis, com foco em centralização de calendários de torneios, análise básica de elegibilidade por perfil/categoria e cobrança de assinaturas.

O projeto é um produto real em fase de MVP contratual com componentes já avançados em desenvolvimento.

A stack atual contempla:

- Backend em Django/Django REST Framework.
- Banco PostgreSQL.
- Redis para filas/cache.
- Celery Worker e Celery Beat para tarefas assíncronas.
- Frontend web.
- Aplicativo mobile React Native/Expo como produto expandido/apoio operacional, embora app nativo não seja obrigação contratual do MVP.
- Railway como infraestrutura principal.
- Cloudinary para imagens.
- Resend para e-mails transacionais.
- Sentry para monitoramento.
- Asaas para pagamentos de assinaturas.
- n8n para automações assistidas/importação operacional de dados.
- Domínio principal: `www.tennis.app.br`.
- API principal: `api.tennis.app.br`.

O backend é a fonte da verdade para regras de negócio, autenticação, permissões, dados externos normalizados, pagamentos, assinaturas e decisões sensíveis.

O mobile e o frontend web devem consumir a API. Eles não devem conter regras críticas de segurança nem chaves privadas.

---

## 2. Escopo contratual do MVP

O MVP contratado consiste no desenvolvimento de uma plataforma digital para jogadores de tênis, com foco em:

1. centralização de calendários de torneios;
2. análise básica de elegibilidade;
3. cobrança de assinaturas;
4. painel administrativo mínimo para gestão de fontes e torneios.

Ao avaliar tarefas, bugs e entregas, a IA deve separar claramente:

- obrigatório para o MVP contratual;
- produto expandido já implementado ou em desenvolvimento;
- pós-MVP;
- dependência externa;
- limitação da fonte;
- melhoria técnica não bloqueante.

A IA não deve tratar funcionalidades fora do escopo contratual como bloqueadoras da entrega do MVP, salvo se o usuário solicitar explicitamente.

---

## 3. Escopo MVP — Extração e consolidação de dados públicos

O MVP deve implementar mecanismos de coleta, consolidação, curadoria e exibição de dados públicos de torneios de instituições definidas pelo contratante, incluindo COSAT/COSANT e entidades brasileiras priorizadas.

Dados mínimos esperados, quando disponíveis na fonte:

- nome do torneio;
- entidade organizadora;
- datas;
- local;
- categorias;
- prazo de inscrição;
- valor;
- link oficial;
- regulamento/documentos;
- critérios de elegibilidade e ranking, quando existentes.

Regras obrigatórias:

- Coletar apenas dados públicos, dados fornecidos pelo administrador ou dados importados/validados por fluxo operacional.
- Nunca inventar torneios, atletas, rankings, pagamentos, inscritos, status ou critérios.
- Quando a fonte não disponibilizar determinada informação, o sistema deve marcar como `unknown`, “indisponível”, “não informado” ou equivalente amigável.
- Fontes instáveis, bloqueadas ou sem API pública devem ser tratadas com link oficial, curadoria manual, importação assistida ou processo de revisão.
- Automações completas sem revisão manual estão fora do MVP contratual.
- A origem dos dados deve ser preservada sempre que possível por `source_url`, `source_name`, `source_label`, `synced_at`, `confidence`, artefato de ingestão ou log administrativo.

---

## 4. Escopo MVP — Centralização dos calendários

O MVP deve oferecer calendário/listagem unificada de torneios com:

- visualização consolidada;
- filtros por data;
- filtros por local;
- filtros por entidade/fonte;
- filtros por categoria;
- página de detalhe do torneio;
- preservação da fonte e link oficial.

A listagem deve priorizar clareza, confiabilidade e rastreabilidade. Se uma fonte não trouxer dados completos, a interface deve sinalizar a limitação sem quebrar a experiência.

---

## 5. Escopo MVP — Elegibilidade por ranking/categoria

O MVP deve permitir cadastro do perfil do jogador e análise básica de compatibilidade com categorias dos torneios.

A funcionalidade deve contemplar:

- exibição de todas as categorias disponíveis;
- destaque das categorias potencialmente compatíveis;
- sinalização quando a elegibilidade não puder ser confirmada com segurança;
- uso de dados reais do perfil esportista;
- explicação amigável de incompatibilidades ou incertezas.

Regras:

- Não afirmar elegibilidade oficial se os critérios da fonte não forem suficientes.
- Não calcular ranking oficial próprio como se fosse ranking da federação.
- Se critérios/ranking não estiverem disponíveis, usar estado de incerteza explícito.
- A compatibilidade deve ser tratada como apoio ao jogador, não como validação oficial da entidade esportiva.

---

## 6. Escopo MVP — Asaas e assinaturas

O MVP deve integrar com Asaas para:

- criação de clientes;
- criação de assinaturas recorrentes;
- consulta de status;
- cancelamento;
- recebimento de webhooks de pagamento.

Regras críticas:

- Toda integração Asaas deve ficar no backend.
- O mobile/frontend nunca deve conter `ASAAS_API_KEY`.
- O plano só pode ser ativado após confirmação real do pagamento.
- A confirmação deve ocorrer por webhook seguro do Asaas ou consulta segura ao status no backend.
- O usuário nunca deve ter plano alterado apenas por clicar em “OK”, abrir tela, copiar PIX ou iniciar checkout.
- Para PIX, o backend deve retornar ao app apenas dados seguros de exibição: QR Code, Pix copia e cola, status e identificador da cobrança.
- Webhooks devem ser validados com token/HMAC/comparação segura quando aplicável.
- Em sandbox, o comportamento deve se aproximar do fluxo real, mas limitações da conta Asaas devem ser documentadas.

---

## 7. Escopo MVP — Planos Individual e Família

O MVP deve operar com dois conceitos de assinatura:

- **Individual:** 1 usuário titular.
- **Família:** 1 responsável pagante com perfis vinculados, dentro do limite definido no projeto.

Os únicos planos comerciais permitidos no projeto são **Individual** e **Família**. A IA não deve criar, manter ou expandir planos `Free`, `Pro`, `Elite`, `Basic` ou equivalentes como estrutura de produto. Se o código ainda tiver referências antigas a esses nomes, tratar como débito técnico a ser migrado/removido com compatibilidade e sem migração destrutiva. Durante a transição, qualquer seed, serializer, regra de acesso, tela, copy ou integração de pagamento deve apontar para Individual/Família.

Plano Família deve considerar:

- responsável pagante;
- perfis vinculados/dependentes;
- permissões validadas no backend;
- proteção de dados de menores/dependentes;
- dependente não deve gerenciar outros usuários/perfis;
- responsável deve conseguir visualizar/gerenciar perfis vinculados conforme regra do plano;
- mobile/web devem refletir permissões vindas da API, não decidir regras críticas localmente.

Regras:

- Não liberar funcionalidades do Plano Família sem assinatura válida e permissão correta.
- Não simular assinatura ativa com mock.
- Não atualizar plano antes de pagamento confirmado.
- Não criar novos planos fora de Individual/Família.
- Não exibir no mobile/web/admin planos antigos como Free, Pro, Elite ou Basic, exceto em tela técnica de migração/admin quando necessário.
- Documentar migrações, seeds e compatibilidade sempre que mexer em planos.

---

## 8. Escopo MVP — Painel administrativo mínimo

O MVP deve ter painel administrativo mínimo para:

- cadastrar e gerenciar fontes;
- revisar dados importados;
- publicar, editar ou ocultar torneios;
- manter rastreabilidade básica da origem dos dados;
- visualizar erros de ingestão/importação quando disponível;
- acionar ou acompanhar rotinas operacionais quando aplicável.

Regras:

- Endpoints administrativos devem exigir autenticação e permissão adequada.
- Dashboard não deve quebrar se não houver dados.
- Conectores não devem quebrar se não estiverem configurados.
- Erros devem ser tratados com mensagens claras.
- Não exibir secrets, tokens ou payloads sensíveis no painel.

---

## 9. Fora do escopo do MVP contratual

Não fazem parte desta fase contratual, salvo solicitação explícita posterior:

- app nativo para iOS e Android como obrigação contratual;
- integração com todas as federações e entidades do ecossistema;
- inscrição em torneios dentro da plataforma como obrigação do MVP;
- cálculo oficial de ranking próprio;
- sincronização em tempo real com bases fechadas de terceiros;
- split de pagamento, repasse ou operação de marketplace;
- marketplace de produtos, lojas ou vendedores;
- notificações avançadas multicanal;
- motor de recomendação com IA;
- automações completas sem revisão manual;
- painel financeiro avançado;
- múltiplos perfis financeiros no plano Família;
- gestão jurídica/regulatória junto às entidades esportivas.

Funcionalidades existentes ou em desenvolvimento que ultrapassem esse escopo devem ser classificadas como produto expandido, apoio operacional ou pós-MVP, e não como bloqueio obrigatório para aceitar o MVP contratual.

---

## 10. Produto expandido / pós-MVP

O projeto já pode conter ou vir a conter funcionalidades acima do MVP contratual, como:

- app mobile React Native/Expo;
- watchlist;
- alertas avançados;
- lista de inscritos;
- status de pagamento por atleta;
- regra de substituição por ranking;
- n8n para automação/importação assistida;
- ranking por federação quando disponível;
- integração com múltiplas fontes;
- fluxos de inscrição internos;
- melhorias de UX mobile;
- EAS build;
- staging/CI/CD;
- marketplace.

Essas funcionalidades podem ser mantidas ou evoluídas, mas a IA deve sempre indicar se pertencem ao MVP contratual, produto expandido ou pós-MVP.

---

## 11. Resultado esperado do MVP

Ao final do MVP, a plataforma deve permitir:

- consolidar torneios de fontes selecionadas em uma única interface;
- mostrar ao jogador quais categorias são potencialmente compatíveis com seu perfil;
- disponibilizar assinatura paga via Asaas;
- operar com planos Individual e Família;
- permitir gestão administrativa básica das fontes e torneios;
- preservar a fonte oficial e a rastreabilidade dos dados.

---

## 12. Repositório

Repositório principal:

```txt
https://github.com/bWSantos7/tennis_hub.git
```

Sempre respeitar a estrutura atual do projeto. Não alterar arquitetura sem justificativa clara.

---

## 13. Arquitetura esperada

A arquitetura atual contempla os seguintes blocos:

```txt
Frontend Web
Mobile App React Native/Expo
Backend Django API
PostgreSQL
Redis
Celery Worker
Celery Beat
Cloudinary
Resend
Sentry
Asaas
Railway
n8n
```

O backend é a fonte da verdade para regras de negócio, autenticação, pagamentos, permissões e dados sensíveis.

O mobile e o frontend web devem consumir a API. Eles não devem conter regras críticas de segurança nem chaves privadas.

---

## 14. URLs e domínios corretos

Utilizar preferencialmente os domínios finais:

```txt
Frontend web:
https://www.tennis.app.br

Backend/API:
https://api.tennis.app.br
```

Evitar usar URLs antigas do Railway no código final, exceto quando necessário para debug ou healthcheck.

URLs Railway antigas não devem ser usadas como base definitiva no app mobile ou frontend web.

---

## 15. Papéis dos agentes de IA

O fluxo operacional recomendado é:

```txt
Claude = executor principal: cria, altera código, roda testes, documenta e entrega relatório.
Codex = revisor/auditor: revisa diff, riscos, edge cases e testes, sem alterar nada salvo autorização explícita.
Usuário = aprova push, deploy, migrations, alterações sensíveis e decisões de escopo.
```

O Claude não deve gastar tempo fazendo auditoria ampla duplicada se o Codex será usado como auditor posterior. O Claude deve focar em execução segura, testes e relatório técnico objetivo.

O Codex não deve alterar arquivos, executar comandos destrutivos, rodar migrations, fazer commit, push ou deploy sem autorização explícita.

---

## 16. Variáveis de ambiente e segurança

Nunca commitar arquivos `.env`.

Nunca expor secrets no frontend web ou mobile.

Nunca colocar no código:

- SECRET_KEY
- DATABASE_URL
- REDIS_URL
- REDIS_PASSWORD
- POSTGRES_PASSWORD
- RESEND_API_KEY
- CLOUDINARY_URL
- ASAAS_API_KEY
- ASAAS_WEBHOOK_TOKEN
- IMPORT_API_TOKEN
- TENNIS_IMPORT_TOKEN
- VAPID_PRIVATE_KEY
- SENTRY_DSN
- qualquer outra chave sensível

Se alguma chave sensível aparecer no repositório, prints, logs ou workflow, considerar comprometida e solicitar rotação imediata.

O projeto já teve chaves sensíveis compartilhadas durante o desenvolvimento. Portanto, sempre priorizar hardening e rotação de secrets quando necessário.

---

## 17. Regras críticas de produção

Em produção:

- Não usar SQLite.
- Não permitir fallback silencioso para SQLite.
- Não usar `ALLOWED_HOSTS=*`.
- Não deixar `DEBUG=True`.
- Não expor endpoints administrativos sem autenticação.
- Não expor stack trace para usuário final.
- Não usar mocks para esconder erro real.
- Não atualizar assinatura/plano sem confirmação real de pagamento.
- Não salvar dados sensíveis no AsyncStorage/SecureStore sem critério.
- Não expor chaves privadas no mobile.
- Não usar URLs antigas do Railway como padrão final.
- Não ativar automações destrutivas ou importações definitivas sem `dry_run`, validação e aprovação.

---

## 18. Backend Django

O backend deve concentrar:

- Autenticação.
- Cadastro.
- Login.
- Recuperação de senha.
- Verificação de e-mail.
- Perfil esportista.
- Torneios.
- Elegibilidade.
- Lista/calendário unificado.
- Fontes e conectores.
- Importação assistida.
- Painel admin.
- Pagamentos.
- Webhooks.
- Permissões.
- Integrações externas.

Funcionalidades como inscrições internas, lista nominal de inscritos, rankings por atleta e status financeiro por inscrito são produto expandido, salvo quando estiverem disponíveis publicamente ou forem importadas/validadas por fluxo administrativo.

Ao alterar backend:

1. Identificar causa raiz antes de modificar.
2. Verificar models, serializers, views, permissions, urls e services.
3. Garantir que permissões estejam corretas.
4. Validar respostas da API.
5. Tratar estados de erro e dados vazios.
6. Evitar mudanças quebrando compatibilidade com mobile/web.
7. Não criar migrations desnecessárias.
8. Não alterar dados de produção sem autorização.

---

## 19. Mobile React Native/Expo

O app mobile deve funcionar em Android e iOS via Expo como produto expandido e interface principal atual do usuário.

Regras para o mobile:

- Usar a API correta: `https://api.tennis.app.br`.
- Não usar secrets no app.
- Não implementar regra crítica apenas no mobile.
- Tratar loading, erro e estado vazio.
- Garantir boa usabilidade em telas pequenas.
- Usar `KeyboardAvoidingView`, `ScrollView` e ajustes de teclado quando houver inputs.
- Evitar que o teclado cubra campos.
- Manter identidade visual limpa, moderna e próxima do web.
- Não usar emojis desnecessários em telas profissionais.
- Não deixar textos técnicos aparecendo ao usuário, como nomes de campos do banco/API.
- Não deixar componentes sem sentido, vazios ou quebrados na interface.
- Testar fluxo completo após alterações.

O app mobile não é obrigação contratual do MVP segundo o escopo, mas como já existe no produto, alterações devem preservar qualidade, segurança e compatibilidade.

---

## 20. Frontend web

O frontend web deve manter consistência visual com o produto.

Regras:

- Consumir API correta.
- Não expor secrets.
- Ter estados de loading, erro e vazio.
- Não usar dados mockados em produção.
- Preservar UX limpa e responsiva.
- Garantir compatibilidade com o domínio `www.tennis.app.br`.

---

## 21. Dados externos, fontes e n8n

Fontes prioritárias podem incluir COSAT/COSANT, CBT, FPT e outras entidades brasileiras definidas pelo contratante.

Regras:

- Usar dados públicos ou dados fornecidos/importados pelo administrador.
- Não burlar login, captcha, paywall, autenticação ou bloqueio técnico.
- Não fazer scraping agressivo.
- Sempre que possível, usar APIs oficiais, documentos públicos, páginas abertas, CSV/HTML/texto fornecido ou importação assistida.
- Se a fonte estiver instável/bloqueada, usar link oficial + curadoria manual/importação assistida.
- Automação completa sem revisão manual está fora do MVP.
- n8n pode ser usado como apoio operacional para buscar targets, parsear HTML/CSV/texto e enviar `dry_run` para o backend.
- O fluxo de importação deve priorizar `dry_run=true` e revisão antes de salvar dados reais.
- Não ativar `dry_run=false` automaticamente sem validação e aprovação.

Campos e conceitos importantes:

- `source_url`: página oficial/fonte geral do torneio.
- `entries_source_url`: URL mais próxima da lista de inscritos, quando computável.
- `ranking_source_url`: URL de ranking, quando computável.
- `candidate_entry_links`: links candidatos para inscritos/chaves/ranking.
- `source_name`/`source_label`: origem amigável dos dados.
- `synced_at`: última sincronização/importação.
- `confidence`: nível de confiança (`high`, `medium`, `low`).
- `unknown`: estado correto quando o dado não está disponível.

---

## 22. Torneios

Funcionalidades importantes para o MVP:

- Listagem/calendário unificado de torneios.
- Filtros por data.
- Filtros por local.
- Filtros por entidade/fonte.
- Filtros por categoria.
- Página de detalhe do torneio.
- Fonte oficial e link preservados.
- Dados mínimos conforme disponibilidade da fonte.
- Torneios compatíveis com perfil do usuário.

Produto expandido pode incluir:

- agenda/watchlist;
- alertas;
- lista de inscritos;
- status financeiro por atleta;
- dados de ranking individual;
- automações n8n.

Regras:

- Filtros devem ser validados no backend e no frontend/mobile.
- Se um filtro não retorna dados, investigar payload, query params, serializer, endpoint e banco.
- Não usar mock para simular torneios.
- Torneios compatíveis devem considerar dados reais do perfil esportista.
- Caso não existam torneios compatíveis, exibir mensagem amigável.

---

## 23. Torneios compatíveis

A funcionalidade “Torneios compatíveis com você” deve considerar, conforme disponibilidade no modelo atual:

- Cidade/localização.
- Distância preferida.
- Nível do jogador.
- Categoria.
- Idade.
- Gênero.
- Perfil esportista.
- Preferências configuradas pelo usuário.

Caso faltem dados no perfil, o app deve orientar o usuário a completar ou atualizar o perfil.

Não retornar lista vazia sem explicação.

A elegibilidade deve ser apresentada como potencial/estimada quando não houver regra oficial completa.

---

## 24. Inscrições, rankings e lista de inscritos

Inscrição em torneios dentro da plataforma não é obrigação contratual do MVP.

Lista nominal de inscritos, ranking por atleta, status de pagamento por atleta e situação competitiva são produto expandido, exceto quando disponíveis publicamente, importados pelo administrador ou validados por pipeline confiável.

Quando a informação estiver disponível e puder ser exibida com permissão:

- Quantidade total de inscritos.
- Nome ou identificação permitida do inscrito.
- Categoria.
- Ranking/posição, se disponível.
- Fonte do ranking, se disponível.
- Status da inscrição.
- Status do pagamento, se disponível.
- Confirmado/lista de espera/removido/substituído/pendente/desconhecido.
- Vagas totais/preenchidas/restantes, se disponíveis.
- Origem e última sincronização.

Regras:

- Respeitar privacidade e permissões.
- Usuário comum não deve acessar informações sensíveis indevidas.
- Admin pode ter visão ampliada conforme regra do sistema.
- Não considerar “pagou” como confirmado definitivo quando a entidade puder aplicar substituição por ranking.
- `removed_or_replaced=true` deve prevalecer sobre `payment_status=paid`.
- Se pagamento/ranking/status não estiverem disponíveis, usar `unknown`/“não informado”.
- Não inventar ranking, pagamento, inscrição ou status.

---

## 25. Agenda, watchlist e alertas

Agenda, watchlist e alertas podem existir como produto expandido.

Regras de UI:

- Cards devem ser claros.
- Status não deve ser sobreposto por botões.
- Botão de lixeira/remover deve ficar preferencialmente no canto inferior direito do card.
- Toda exclusão deve pedir confirmação.
- Estado vazio deve ser amigável.
- Após adicionar torneio à agenda/watchlist, o app deve refletir a alteração corretamente.

Alertas:

- Não exibir nomes técnicos de campos ao usuário.
- Exemplo ruim: `entry_close_at`.
- Exemplo correto: `As inscrições encerram em 30/04/2026 às 18:00`.
- Preferências de alertas devem refletir apenas canais suportados.
- Push/in-app devem ser priorizados quando aplicável.
- Notificações avançadas multicanal estão fora do MVP contratual.

---

## 26. Painel administrativo

O painel admin deve permitir gestão e visão operacional do sistema.

Áreas importantes:

- Dashboard.
- Estatísticas.
- Fontes/conectores.
- Torneios.
- Revisão de dados importados.
- Publicar, editar ou ocultar torneios.
- Usuários.
- Assinaturas/pagamentos.
- Logs/monitoramento, quando disponível.

Regras:

- Dashboard não deve quebrar se não houver dados.
- Conectores não devem quebrar se não estiverem configurados.
- Endpoints administrativos devem exigir autenticação/permissão.
- Erros devem ser tratados com mensagens claras.
- Evitar tela branca ou crash.
- Não expor secrets ou payloads sensíveis.

---

## 27. Stats e gráficos

Em telas de estatísticas:

- Gráficos devem ter espaçamento adequado.
- Não devem ficar colados.
- Devem ser legíveis em telas pequenas.
- Deve haver loading, erro e estado vazio.
- Evitar sobrecarga visual.

---

## 28. UX e padrão visual

O visual deve ser:

- Moderno.
- Limpo.
- Esportivo.
- Profissional.
- Coerente com Tennis Hub.
- Responsivo.
- Leve.
- Sem excesso de emojis.
- Sem textos técnicos visíveis ao usuário.

Sempre priorizar clareza, fluidez e experiência mobile/web.

---

## 29. LGPD e privacidade

O sistema deve respeitar LGPD.

Cadastro deve conter aceite de termos/LGPD quando aplicável.

Link oficial da LGPD:

```txt
https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
```

Regras:

- Não coletar dados desnecessários.
- Não expor dados pessoais indevidamente.
- Não mostrar lista de inscritos com informações sensíveis sem permissão.
- Garantir clareza no aceite de termos.
- Exclusões devem pedir confirmação.
- Dados de menores/dependentes no Plano Família exigem permissões e minimização.

---

## 30. E-mails

O projeto utiliza Resend para e-mails transacionais.

Usos esperados:

- Verificação de e-mail.
- Recuperação de senha.
- Eventuais comunicações transacionais necessárias.

Regras:

- Usar domínio validado.
- Preferir remetente do domínio oficial.
- Não usar `onboarding@resend.dev` em produção.
- Não retornar “e-mail enviado” se o Resend falhou.
- Não mascarar erro crítico de envio em logs internos.
- Não usar e-mail como canal de alerta mobile se essa opção foi removida do produto.
- Não expor chave do Resend no frontend/mobile.

---

## 31. Cloudinary

Cloudinary é usado para imagens, como foto de perfil.

Regras:

- Upload deve ser feito de forma segura.
- Não expor credenciais sensíveis no mobile/frontend.
- Validar tamanho e tipo de arquivo quando aplicável.
- Tratar erro de upload.

---

## 32. Sentry

Sentry é usado para monitoramento.

Regras:

- Não registrar dados sensíveis em logs.
- Não enviar secrets para Sentry.
- Usar environment adequado.
- Erros críticos devem ser rastreáveis.

---

## 33. Railway

Infra atual no Railway:

- Frontend.
- Backend.
- Worker/Beat.
- Redis.
- PostgreSQL.

Regras:

- Backend, worker e beat devem ser serviços separados.
- Redis e Postgres devem ser acessados por URL privada interna quando possível.
- Evitar depender de URLs públicas para comunicação interna.
- Não rodar seed automático em todo deploy.
- Migrações devem ser controladas.
- Healthchecks devem estar funcionais.
- Alterações em variáveis de ambiente de produção precisam de confirmação.
- Deploys, migrations e comandos de produção precisam de aprovação explícita quando houver risco.

---

## 34. Custos atuais conhecidos

Custos aproximados atuais:

- Domínio: R$40 anual.
- Claude Pro: cerca de R$118,87 mensal.
- Railway Pro: cerca de R$108,23 mensal.
- Resend: plano Free.
- Cloudinary: plano Free.
- Sentry: plano Free.

Custo mensal aproximado informado: R$267,10.

Ao sugerir mudanças de infraestrutura, considerar custo-benefício.

---

## 35. Proibições para IA

A IA não deve:

- Expor secrets.
- Criar ou commitar `.env`.
- Alterar plano do usuário sem pagamento confirmado.
- Usar mocks para mascarar erro.
- Inventar dados externos.
- Remover funcionalidades sem justificativa.
- Trocar arquitetura sem aprovação.
- Usar SQLite em produção.
- Usar `ALLOWED_HOSTS=*`.
- Deixar `DEBUG=True`.
- Ignorar autenticação/permissões.
- Colocar lógica sensível no mobile.
- Usar URL Railway antiga como API principal.
- Ignorar testes.
- Criar endpoints sem permissão.
- Exibir campos técnicos ao usuário.
- Deixar telas sem tratamento de loading/erro/vazio.
- Fazer alterações grandes sem explicar impacto.
- Tratar funcionalidades fora do escopo como bloqueadoras do MVP sem autorização.
- Ativar `dry_run=false`, Cron de importação, deploy, push ou migration sem confirmação quando houver risco.

---

## 36. Processo obrigatório antes de alterar código

Antes de qualquer alteração:

1. Ler este arquivo.
2. Entender o escopo contratual do MVP.
3. Separar o pedido em MVP obrigatório, produto expandido, pós-MVP, dependência externa ou limitação da fonte.
4. Entender a arquitetura atual.
5. Identificar a causa raiz do problema.
6. Localizar arquivos envolvidos.
7. Verificar impacto em backend, web e mobile.
8. Evitar alterações desnecessárias.
9. Planejar solução segura.

---

## 37. Processo obrigatório após alterar código

Após qualquer alteração:

1. Rodar testes disponíveis.
2. Rodar lint/typecheck, se existirem.
3. Verificar build do mobile quando aplicável.
4. Verificar build/check do backend quando aplicável.
5. Testar fluxo manualmente quando possível.
6. Conferir se não há secrets no código.
7. Conferir se URLs estão corretas.
8. Conferir se não houve quebra visual.
9. Conferir permissões/autenticação.
10. Documentar o que foi alterado.
11. Separar pendências em MVP, produto expandido, pós-MVP, dependência externa e limitação da fonte.

---

## 38. Checklist de validação

Sempre que mexer no projeto, validar o que for aplicável ao escopo da alteração:

- Login.
- Cadastro.
- Verificação de e-mail.
- Recuperação de senha.
- Perfil esportista.
- Listagem/calendário de torneios.
- Filtros.
- Torneios compatíveis.
- Detalhe do torneio.
- Fonte oficial/link oficial.
- Elegibilidade básica.
- Lista de inscritos, se aplicável.
- Agenda/watchlist, se aplicável.
- Alertas, se aplicável.
- Pagamentos.
- Troca de plano.
- PIX.
- Plano Individual.
- Plano Família.
- Painel admin.
- Gestão de fontes.
- Revisão/publicação/ocultação de torneios.
- Stats.
- Upload de imagem.
- Responsividade mobile.
- Permissões.
- Logs de erro.
- n8n/importação assistida, quando aplicável.

---

## 39. Formato esperado de resposta da IA

Ao finalizar uma tarefa, a IA deve retornar:

```txt
Resumo da correção:
- ...

Classificação de escopo:
- MVP obrigatório / Produto expandido / Pós-MVP / Dependência externa / Limitação da fonte

Arquivos alterados:
- ...

Causa raiz:
- ...

Solução aplicada:
- ...

Como testar:
- ...

Riscos ou pendências:
- ...

Comandos executados:
- ...

Validação final:
- ...
```

Não considerar uma tarefa concluída apenas porque o app compilou.

A tarefa só está concluída quando a funcionalidade foi testada e validada, ou quando limitações externas estiverem claramente documentadas.

---

## 40. Prioridade máxima atual

Prioridades gerais do Tennis Hub:

1. Segurança.
2. MVP contratual.
3. Dados reais e rastreáveis, sem mocks.
4. Calendário/listagem consolidada de torneios.
5. Elegibilidade básica por perfil/categoria.
6. Integração Asaas correta.
7. Planos Individual e Família.
8. Painel administrativo mínimo.
9. UX limpa e profissional.
10. Estabilidade da API.
11. Mobile funcional como produto expandido.
12. n8n/importação assistida com revisão manual quando aplicável.
13. Redução de custos sem comprometer produção.

A IA não deve expandir escopo sem aprovação. Funcionalidades pós-MVP devem ser documentadas como backlog, não tratadas automaticamente como bloqueadoras.

---

## 41. Observação final

Este projeto deve ser tratado como produto real.

Toda alteração deve ser feita com cuidado, pensando em produção, segurança, usuário final, escopo contratual, rastreabilidade, escalabilidade e manutenção futura.
