# Checklist de submissão — App Tenfy iOS (App Store)

Contexto: o app iOS é uma casca Expo/WebView que carrega `https://tenfy.com.br`, operando
em **modo login apenas** (cadastro e assinatura ficam fora do app — conformidade Apple
3.1.1). O **retorno automático logado** (universal links + handoff) já está implementado.
Veja [universal-links.md](../integrations/universal-links.md).

Use este checklist na ordem. Itens marcados ✅ já estão prontos no código.

---

## Fase 0 — Contas e credenciais (bloqueante, é o primeiro passo)

- [ ] **Apple Developer Program** (US$ 99/ano) — https://developer.apple.com/programs/
  - Pessoa física: ativa em horas.
  - Organização (recomendado p/ empresa): exige número **D-U-N-S** (pode levar dias).
- [ ] Aceitar contratos no **App Store Connect** (ASC) e configurar **Agreements, Tax, and Banking**
      (obrigatório mesmo para app gratuito sem IAP).
- [ ] Criar o registro do app no ASC:
  - Nome: `Tenfy`
  - Bundle ID: `com.tenfy.mobile` (registrar em Certificates, IDs & Profiles)
  - Idioma primário: Português (Brasil)
  - Categoria: **Sports** (secundária opcional)
- [ ] Anotar os IDs e preencher [mobile/eas.json](../../mobile/eas.json) → `submit.production.ios`:
  - `appleId` (e-mail da conta Apple)
  - `ascAppId` (App Store Connect → App → App Information → "Apple ID" numérico)
  - `appleTeamId` (Membership → Team ID, 10 caracteres)
- [ ] Preencher placeholders dos universal links:
  - AASA: `REPLACE_WITH_APPLE_TEAM_ID` em
    [frontend/public/.well-known/apple-app-site-association](../../frontend/public/.well-known/apple-app-site-association)
  - assetlinks: `REPLACE_WITH_PLAY_APP_SIGNING_SHA256_FINGERPRINT`
- [ ] **Validar hosting** do `.well-known` após deploy do frontend:
      `curl -i https://tenfy.com.br/.well-known/apple-app-site-association`
      → precisa **200**, `Content-Type: application/json`, **sem redirect**, HTTPS.

---

## Fase 1 — Configuração técnica do app

- [x] `bundleIdentifier`, `deploymentTarget` (15.1), `newArchEnabled`, `associatedDomains` — [mobile/app.json](../../mobile/app.json)
- [x] Permissões `infoPlist` (câmera, fotos) com textos em PT
- [ ] **Ícone 1024×1024** PNG **sem canal alpha/transparência** (Apple rejeita com alpha) — conferir `assets/logo4.png`
- [ ] `version` e `buildNumber` coerentes (production usa `autoIncrement` no EAS) — [mobile/app.json](../../mobile/app.json)
- [ ] **Privacy Manifest** (`PrivacyInfo.xcprivacy`): o Expo 54 gera automaticamente; confirmar no build
      se há "required reason APIs" a declarar.
- [ ] **Export compliance**: app só usa HTTPS padrão → adicionar
      `ITSAppUsesNonExemptEncryption=false` no `infoPlist` para evitar a pergunta a cada build.

---

## Fase 2 — Conformidade e gates de revisão

- [x] **3.1.1 (In-App Purchase)**: app iOS **não** exibe planos/preços/checkout (login apenas) —
      auditado no código (register redireciona, paywall não renderiza, assinatura é read-only).
      Base: **3.1.3(b) Multiplatform Services** — assinatura adquirida no site, sem direcionar à
      compra dentro do app. Testar no build real que nenhuma tela mostra compra.
- [x] **Sign in with Apple (4.8)**: N/A — não há login social de terceiros.
- [x] **Política de privacidade**: `https://tenfy.com.br/politica-privacidade` (também linkada
      in-app no Perfil → Privacidade e dados).
- [x] **Exclusão de conta no app (5.1.1 v)**: botão "Excluir minha conta" no Perfil (+ página
      pública `https://tenfy.com.br/excluir-conta` e e-mail de fallback).
- [ ] **App Privacy ("nutrition labels")** no ASC — declarar com precisão:
  - **Contact Info**: e-mail, telefone, nome → vinculados à identidade.
  - **Sensitive/Identifiers**: CPF (national ID), foto de perfil.
  - **User Content / Usage Data**: torneios seguidos, uso do app.
  - **Tracking**: **Nenhum** — o app não usa IDFA nem SDKs de rastreio (sem ATT/NSUserTrackingUsageDescription).
  - ⚠️ Dados de **menores/dependentes**: declarar e **não** marcar Kids Category.
- [ ] **Age Rating**: preencher questionário (sem conteúdo adulto → provável 4+).
- [x] **Privacy Manifest (`PrivacyInfo.xcprivacy`)**: gerado automaticamente pelo Expo/EAS a partir
      dos pacotes (WebView, notifications, constants). Conferir presença no build; nada manual no repo.
- [x] **4.2 (Minimum Functionality)**: mitigado com **push nativo** (expo-notifications + APNs),
      além de sessão persistente, deep link/retorno automático e câmera p/ avatar. Na resposta ao
      revisor, destacar essas capacidades nativas. Requer o passo de credenciais APNs no build (Fase 4).
- [ ] **Conta de demonstração** para o revisor: criar um usuário **com assinatura ativa** e informar
      e-mail/senha em "App Review Information" (garante que o revisor veja o app completo).

---

## Fase 3 — Metadados e assets de loja (ASC)

- [ ] **Screenshots iPhone 6.7"** (obrigatório) — ex.: 1290×2796. iPad não é necessário
      (`supportsTablet: false`).
- [ ] Subtítulo, descrição, palavras-chave, URL de suporte, URL de marketing.
- [ ] Ícone da loja 1024 (sem alpha).
- [ ] **Notas para o revisor** (texto sugerido):
  > "O Tenfy é um app de acompanhamento de torneios de tênis. A criação de conta e a
  > assinatura são feitas no site (tenfy.com.br); o app opera com login de contas já
  > existentes. Conta de teste com acesso ativo: <email> / <senha>."

---

## Fase 4 — Build e TestFlight

- [ ] **Push nativo (APNs)**: no primeiro `eas build` do iOS, deixar o EAS gerar/registrar a
      **APNs Key** (precisa da conta Apple). Sem isso o app instala, mas o push não entrega.
      O código já está pronto (token + registro + envio via Expo); falta só a credencial.
- [ ] `cd mobile && eas build --platform ios --profile preview`
- [ ] Instalar via **TestFlight** (grupo interno) e testar no device real:
  - [ ] Login funciona; **não há** "Criar conta" nem planos/preços/checkout
  - [ ] Câmera / foto de perfil (permissões aparecem com os textos certos)
  - [ ] **Retorno automático**: assinar no Safari → "Abrir no app" → entra logado
        (depende do AASA publicado com Team ID correto)
  - [ ] **Push nativo**: aceitar permissão; verificar token registrado em
        `/api/alerts/register-device/`; receber notificação e, ao tocar, abrir a tela certa
  - [ ] Voltar (gesto), estados de loading/erro/sem conexão
- [ ] `eas build --platform ios --profile production`

---

## Fase 5 — Envio para revisão

- [ ] `eas submit --platform ios --profile production` (ou subir o `.ipa` no Transporter)
- [ ] No ASC: anexar o build à versão, responder **App Privacy** e **Export Compliance**
- [ ] Preencher "App Review Information" (conta demo + notas)
- [ ] **Submit for Review**

---

## Riscos a vigiar na 1ª revisão

1. **4.2 (wrapper)** — mitigado com push nativo (`expo-notifications` + APNs) já implementado,
   somado a sessão persistente, deep link/retorno automático e câmera. Se ainda houver objeção,
   responder destacando essas capacidades nativas.
2. **3.1.1** — garantir zero menção a compra no app iOS (já tratado no código; reconferir no build).
3. **Hosting do `.well-known`** — se a AASA não for servida corretamente, o retorno automático
   silenciosamente não abre o app (cai no Safari). Validar antes de submeter.
