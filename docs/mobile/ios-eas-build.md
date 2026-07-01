# Build iOS via EAS (sem Mac) — runbook do Tenfy

Como compilar e publicar o app iOS do Tenfy usando o **EAS Build** (nuvem da
Expo). Os builds rodam em **macOS na nuvem** — você dispara tudo do **Windows**.

> **Resumo de custo:** EAS plano **Free** (15 builds iOS/mês) = **US$ 0**. O único
> custo obrigatório é o **Apple Developer Program: US$ 99/ano** (necessário para
> build em dispositivo, TestFlight e App Store). Push da Expo = grátis.

---

## Contas necessárias

| Conta | Custo | Para quê |
|---|---|---|
| **Expo** (expo.dev) | grátis | disparar os builds no EAS |
| **Apple Developer Program** | US$ 99/ano | assinar/distribuir (device, TestFlight, App Store) |

---

## Passo 0 — Login (uma vez, no Windows)

```bash
cd mobile
npm install
npx eas login          # sua conta Expo
```

O projeto já está vinculado (veja `owner` e `extra.eas.projectId` em `app.json`),
então não é preciso `eas init`.

---

## Passo A — Build de teste no Simulador (NÃO precisa de conta Apple)

Serve para **validar o pipeline do EAS agora**, antes de ter a conta Apple. Gera
um `.app` para o **Simulador do iOS** (roda num Mac com Xcode/Simulador):

```bash
npm run build:ios:sim      # eas build --platform ios --profile simulator
```

- Não pede credenciais Apple (build de simulador é unsigned).
- Ao terminar, o EAS dá um link para baixar o `.app`. No Mac:
  `unzip` → arrastar para o Simulador, ou `xcrun simctl install booted <App>.app`.

> Isso prova que o app compila no EAS. Para rodar em **iPhone físico**,
> TestFlight ou App Store, é obrigatório o Passo B (conta Apple).

---

## Passo B — Build de produção + envio (precisa da conta Apple)

### B1. Build
```bash
npm run build:ios:prod     # eas build --platform ios --profile production
```

No **primeiro** build o EAS cuida das credenciais automaticamente:
- pede login com seu **Apple ID**;
- registra o **Bundle ID** `com.tenfy.mobile` (se ainda não existir);
- gera **Distribution Certificate** + **Provisioning Profile**;
- oferece criar a **chave de Push (APNs)** — aceite (necessária para notificações).

Tudo fica guardado no EAS. Para revisar/reconfigurar depois: `npx eas credentials`.

### B2. Envio para a App Store / TestFlight
```bash
npm run submit:ios         # eas submit --platform ios --profile production
```

Isso exige 3 dados no `mobile/eas.json` (hoje `FILL_IN_*`). Onde obter cada um
**depois** de criar o app no [App Store Connect](https://appstoreconnect.apple.com):

| Campo em `eas.json` | O que é | Onde achar |
|---|---|---|
| `appleId` | seu e-mail Apple | o e-mail da conta Apple Developer |
| `appleTeamId` | Team ID (10 caracteres) | Apple Developer → **Membership** |
| `ascAppId` | ID numérico do app | App Store Connect → app → **App Information → Apple ID** |

Se preferir, deixe esses campos vazios/removidos e o `eas submit` **pergunta
interativamente** no envio.

Após o `submit`, o build aparece em **TestFlight** (para testar) e pode ser
promovido para **App Store** no App Store Connect (metadados prontos em
[`app-store-metadata.md`](./app-store-metadata.md)).

---

## Versão e build number

- `version` (ex.: 1.0.10) vem do `app.json` → vira o CFBundleShortVersionString.
- O **build number** é incrementado automaticamente a cada build de produção
  (`autoIncrement: true` no perfil `production` do `eas.json`). Não precisa mexer.
- Para uma nova versão pública, suba o `version` no `app.json`.

---

## Observações importantes

- **Projeto tem `ios/` versionado** (fluxo prebuild/bare): o EAS usa essa pasta e
  roda `pod install` no worker macOS dele. Mudanças no `app.json` **não** se
  refletem sozinhas no nativo — para regenerar seria `npx expo prebuild -p ios --clean`
  (num Mac/Linux; sobrescreve edições manuais no `ios/`).
- **Fila do plano Free** é de baixa prioridade — um build pode esperar de minutos
  a algumas horas. Se incomodar, o plano **Starter (US$ 19/mês)** dá fila rápida.
- **Universal links:** para o retorno automático funcionar, o arquivo
  `https://tenfy.com.br/.well-known/apple-app-site-association` precisa ter o
  **Team ID real** (hoje `REPLACE_WITH_APPLE_TEAM_ID`).
- **Sem segredos no app:** login/pagamentos ficam no site/backend.

---

## Checklist do primeiro lançamento

- [ ] `npx eas login`
- [ ] (opcional) `npm run build:ios:sim` — validar o pipeline
- [ ] Assinar o **Apple Developer Program** (US$ 99/ano)
- [ ] `npm run build:ios:prod` — deixar o EAS gerar certificados + APNs
- [ ] Criar o app no **App Store Connect** (bundle `com.tenfy.mobile`)
- [ ] Preencher `appleId` / `appleTeamId` / `ascAppId` no `eas.json`
- [ ] `npm run submit:ios` → aparece no **TestFlight**
- [ ] Colocar **Team ID real** na AASA do site
- [ ] Preencher metadados e enviar para revisão na App Store
