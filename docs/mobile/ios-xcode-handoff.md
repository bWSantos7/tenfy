# Entrega iOS — build no Xcode (Tenfy)

Guia para quem vai **compilar e/ou publicar o app iOS do Tenfy no Xcode**.

O app é feito em **Expo (React Native)**. A pasta nativa `mobile/ios/` foi gerada
com `expo prebuild` e está versionada neste repositório. O app é, na prática, um
**WebView** que carrega o site (`tenfy.com.br`) com login nativo, push e
retorno automático via universal links — não há telas nativas complexas.

> **Bundle identifier:** `com.tenfy.mobile`
> **Versão:** 1.0.10 · **Deployment target:** iOS 15.1 · **Arquitetura:** New Architecture (Hermes)

---

## 1. Pré-requisitos (macOS)

O iOS **só compila em macOS** (Xcode é exclusivo de Mac).

| Ferramenta | Versão recomendada |
|---|---|
| macOS | 13+ (Ventura ou superior) |
| Xcode | 16+ (com Command Line Tools) |
| Node.js | 20.19+ ou 22.x |
| Ruby + CocoaPods | CocoaPods 1.15+ (`sudo gem install cocoapods`) |
| Watchman (opcional) | `brew install watchman` |
| Conta Apple Developer | **obrigatória** para assinar/publicar (paga, US$99/ano) |

---

## 2. Setup do projeto

Na raiz do repositório:

```bash
cd mobile

# 1) Dependências JavaScript (não são versionadas)
npm install

# 2) Variáveis de ambiente (aponta o app para a API/site de produção)
cp .env.example .env
#   EXPO_PUBLIC_API_BASE_URL=https://api.tenfy.com.br
#   EXPO_PUBLIC_WEB_URL=https://tenfy.com.br   (adicione se não estiver no .env)

# 3) CocoaPods — CRIA o Tenfy.xcworkspace (não existe até rodar isto)
cd ios && pod install && cd ..
```

> ⚠️ **Sempre abra o `.xcworkspace`, nunca o `.xcodeproj`:**
> ```bash
> open ios/Tenfy.xcworkspace
> ```
> O `Tenfy.xcworkspace` só passa a existir **depois** do `pod install`.

---

## 3. Assinatura (Signing) no Xcode

No Xcode, selecione o target **Tenfy** → aba **Signing & Capabilities**:

1. Marque **Automatically manage signing**.
2. Em **Team**, selecione a equipe da **conta Apple Developer** do Tenfy.
3. Confirme o **Bundle Identifier**: `com.tenfy.mobile`.

### Capabilities já declaradas no projeto (via `Tenfy.entitlements`)
- **Push Notifications** → `aps-environment` (precisa de uma **chave APNs** na conta Apple).
- **Associated Domains** → `applinks:tenfy.com.br` (retorno automático ao app).

Nenhuma capability adicional é necessária.

---

## 4. Rodar / arquivar

- **Simulador:** escolha um iPhone no seletor de destino e clique ▶︎ (Run).
- **Dispositivo físico:** conecte o iPhone, selecione-o e Run (exige signing válido).
- **Arquivar para a App Store:**
  1. Selecione destino **Any iOS Device (arm64)**.
  2. Menu **Product → Archive**.
  3. No Organizer → **Distribute App → App Store Connect**.

> O bundle JavaScript é empacotado automaticamente pelo script de build do
> React Native durante o Archive (release). Não é preciso rodar o Metro à mão
> para arquivar.

---

## 5. Pendências que dependem da conta Apple

Estes itens **não** estão no código porque exigem a conta Apple Developer ativa:

| Item | Onde / como |
|---|---|
| **Team ID** | Apple Developer → Membership. Necessário nos 2 itens abaixo. |
| **Chave APNs (.p8)** | Apple Developer → Keys → criar chave "Apple Push Notifications service". Usada para enviar push (via Expo/EAS ou servidor). |
| **App Store Connect** | Criar o app record (bundle `com.tenfy.mobile`) e preencher metadados. Textos prontos em [`app-store-metadata.md`](./app-store-metadata.md). |
| **Universal Links (AASA)** | No site, `https://tenfy.com.br/.well-known/apple-app-site-association` precisa ter o **Team ID real** no lugar de `REPLACE_WITH_APPLE_TEAM_ID` (arquivo em `frontend/public/.well-known/apple-app-site-association`). |
| **`eas.json`** (se usar EAS) | Preencher `appleId`, `ascAppId`, `appleTeamId` (hoje `FILL_IN_*`) em `mobile/eas.json`. |

---

## 6. Alternativa: build na nuvem (EAS, sem Mac)

Este projeto também builda pela nuvem da Expo — **não precisa de Mac**:

```bash
cd mobile
npm run build:ios:prod     # eas build --platform ios --profile production
npm run submit:ios         # eas submit --platform ios --profile production
```

Requer login no EAS (`npx eas login`) e as credenciais Apple configuradas
(o EAS pode gerá-las automaticamente com a conta Apple).

---

## 7. Observações importantes

- **`mobile/ios/` é código gerado** a partir do `mobile/app.json`. Se alguém rodar
  `npx expo prebuild --platform ios --clean`, a pasta é **regenerada e customizações
  manuais no nativo são perdidas**. Prefira alterar o `app.json`/config plugins e
  regenerar, em vez de editar arquivos nativos à mão.
- **Não versionar:** `ios/Pods/`, `ios/build/`, `xcuserdata/` (já cobertos pelo
  `.gitignore`). Rode `pod install` localmente.
- **API/ambiente:** o app lê `EXPO_PUBLIC_API_BASE_URL` e `EXPO_PUBLIC_WEB_URL`.
  Produção: `https://api.tenfy.com.br` e `https://tenfy.com.br`.
- **Sem segredos no app:** o app não deve conter chaves Asaas/Apple; login e
  pagamentos são resolvidos no site/backend.

---

## Checklist rápido

- [ ] `npm install`
- [ ] `.env` com `EXPO_PUBLIC_API_BASE_URL` e `EXPO_PUBLIC_WEB_URL`
- [ ] `cd ios && pod install`
- [ ] Abrir `ios/Tenfy.xcworkspace`
- [ ] Signing → selecionar **Team** da conta Apple
- [ ] Criar **chave APNs** e **app no App Store Connect**
- [ ] Colocar **Team ID real** na AASA do site
- [ ] Product → Archive → Distribute
