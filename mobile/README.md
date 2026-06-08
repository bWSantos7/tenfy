# Tenfy Mobile

Casca nativa Expo que carrega o app web do Tenfy (`https://tenfy.com.br`) dentro de uma **WebView**. A experiência é o próprio frontend web, garantindo paridade total — toda a lógica (auth, navegação, dados) vive no web; o app trata apenas do chrome nativo, estado de loading e erro de conexão.

> Ajustes de UI/funcionalidade são feitos no `frontend/`, não aqui.

## Variáveis de ambiente

```env
# URL do app web que a WebView carrega
EXPO_PUBLIC_WEB_URL=https://tenfy.com.br
```

## Rodar localmente

```bash
cd mobile
npm install
npx expo start
```

## Build (EAS)

```bash
npm run build:android:preview   # APK de teste
npm run build:android:prod      # produção Android (app bundle)
npm run build:ios:prod          # produção iOS
```
