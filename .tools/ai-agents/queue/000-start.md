# Tarefa inicial dos agentes - Auditoria completa + entrega MVP

Antes de qualquer alteração, leia obrigatoriamente os arquivos:
- CLAUDE.md
- AI_CONTEXT.md
- README.md
- C:\Users\Usuario\Desktop\tennis_hub\escopo_contrato

Siga todas as regras, restrições, arquitetura, checklist e escopo definidos nesses arquivos.

## Contexto

Este projeto é o Tennis Hub.

Estrutura principal:
- backend/
- frontend/
- mobile/
- docs/
- CLAUDE.md
- AI_CONTEXT.md
- README.md
- escopo_contrato

Agentes:
- Claude: executor principal.
- GPT/Codex: auditor técnico, segurança, arquitetura, diff e aderência ao escopo.
- Gemini: QA, UX, mobile, documentação e testes.
- Planner: cria automaticamente as próximas tasks até a entrega final.

## Objetivo principal

Trabalhar automaticamente nesta branch para deixar o projeto 100% pronto para MVP, comparando tudo com o arquivo/pasta:

C:\Users\Usuario\Desktop\tennis_hub\escopo_contrato

O projeto deve ser auditado, corrigido, refatorado e validado até estar de acordo com o escopo contratado.

## Primeira missão obrigatória

Antes de alterar código pesado, fazer uma auditoria completa do projeto.

A auditoria deve comparar:

1. O que existe hoje no projeto.
2. O que está definido no escopo_contrato.
3. O que está documentado em CLAUDE.md e AI_CONTEXT.md.
4. O que falta para o MVP.
5. O que está parcialmente implementado.
6. O que está implementado mas com problema.
7. O que está fora do escopo.
8. O que representa risco técnico, segurança, UX ou produto.

Gerar um relatório inicial detalhado em:

.tools/ai-agents/reports/AUDITORIA-INICIAL-ESCOPO.md

Esse relatório deve conter:

# Auditoria Inicial do Projeto x Escopo Contratado

## Resumo executivo

## Escopo analisado

## Aderência geral ao escopo
Dar uma nota de 0 a 100.

## Backend
- O que está correto
- O que está pendente
- O que está com problema
- O que precisa ser corrigido

## Frontend
- O que está correto
- O que está pendente
- O que está com problema
- O que precisa ser corrigido

## Mobile
- O que está correto
- O que está pendente
- O que está com problema
- O que precisa ser corrigido

## Filtros
Analisar especialmente filtros que não estavam funcionando corretamente.

## Design mobile
Analisar telas, usabilidade, clareza visual, navegação, estados vazios, loading, erros e sucesso.

## Segurança

## Performance

## Testes/checks

## Documentação

## Pendências bloqueantes

## Pendências altas

## Pendências médias

## Pendências baixas

## Backlog recomendado para execução automática

## Ordem de execução recomendada

## Critério para considerar o MVP pronto

## Execução após auditoria

Depois da auditoria inicial, os agentes devem criar tasks automáticas na fila:

.tools/ai-agents/queue/

As tasks devem seguir esta prioridade:

1. Corrigir problemas bloqueantes encontrados na auditoria.
2. Corrigir filtros que não funcionam.
3. Refatorar todas as telas do mobile.
4. Melhorar design, usabilidade e clareza do app mobile.
5. Corrigir fluxos principais do MVP.
6. Corrigir backend/APIs necessários para o MVP.
7. Corrigir frontend web se houver pendências.
8. Criar ou ajustar testes/checks.
9. Atualizar documentação.
10. Gerar relatório final.

## Mobile - prioridade especial

A pasta mobile/ deve ser revisada e refatorada de ponta a ponta.

Objetivos para mobile:
- Melhorar todas as telas.
- Melhorar navegação.
- Melhorar usabilidade.
- Melhorar design visual.
- Melhorar clareza das informações.
- Corrigir filtros que não estão funcionando.
- Corrigir estados vazios.
- Corrigir estados de loading.
- Corrigir mensagens de erro.
- Corrigir inconsistências visuais.
- Garantir aderência ao escopo_contrato.
- Manter compatibilidade com o backend existente.
- Evitar quebrar funcionalidades já existentes.

O app mobile pode receber melhorias visuais significativas, desde que respeite o objetivo do produto e não remova funcionalidades importantes.

## Regras de autonomia

- Não pedir confirmação humana para alterações normais dentro desta branch.
- Pode editar código.
- Pode criar arquivos.
- Pode refatorar.
- Pode melhorar UI/UX.
- Pode corrigir bugs.
- Pode criar testes.
- Pode atualizar documentação.
- Pode rodar lint, test, build e checks locais.
- Pode criar novas tasks automaticamente.
- Pode executar ciclos sucessivos até gerar FINAL-REPORT.md.

## Limites obrigatórios

- Não fazer deploy.
- Não fazer push para main.
- Não alterar secrets reais.
- Não executar comandos em banco de produção.
- Não mexer em billing real.
- Não alterar Railway produção.
- Não alterar Asaas produção.
- Não alterar Resend produção.
- Não alterar Cloudinary produção.
- Não apagar arquivos em massa sem justificar em relatório.
- Não remover funcionalidades sem explicar.
- Não marcar como pronto se houver pendência bloqueante.

## Critério de parada

Parar somente quando for criado:

.tools/ai-agents/reports/FINAL-REPORT.md

O relatório final deve conter:

# Relatório Final dos Agentes

## Veredito final
Use:
- mvp_pronto
- mvp_pronto_com_ressalvas
- mvp_nao_pronto

## Nota final de aderência ao escopo
De 0 a 100.

## Comparativo final com escopo_contrato

## O que foi implementado

## O que foi corrigido

## O que foi refatorado no mobile

## Filtros corrigidos

## Testes/checks executados

## Riscos restantes

## Pendências manuais

## O que precisa ser configurado manualmente

## Recomendação antes de merge/deploy

## Status final

## Primeira ação esperada

Iniciar pela auditoria completa do projeto contra o escopo_contrato e criar o relatório:

.tools/ai-agents/reports/AUDITORIA-INICIAL-ESCOPO.md

Depois disso, criar automaticamente a próxima task de execução na fila.
