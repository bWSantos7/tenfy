# Tenfy Brand Assets — Mobile

Assets extraídos do Manual da Marca Tenfy para uso no app mobile React Native/Expo.

## Cores oficiais

| Nome        | Hex       | Uso                                 |
|-------------|-----------|-------------------------------------|
| Azul Profundo | `#0A1330` | Background dark, CTA light mode   |
| Lima Tênis  | `#C6EF21` | Accent, CTA dark mode, badges     |
| Laranja Barro | `#FF6A00` | Status, alertas, destaques       |
| Off-white   | `#F6F7FA` | Background light mode             |
| Grafite     | `#1D232D` | Card dark mode                    |

## Assets Expo prontos para uso

Os assets principais do Expo já foram gerados e estão em `mobile/assets/`:

| Arquivo               | Tamanho   | Descrição                        |
|-----------------------|-----------|----------------------------------|
| `icon.png`            | 1024×1024 | Ícone do app (Tenfy dark icon)  |
| `adaptive-icon.png`   | 1024×1024 | Android adaptive icon (RGBA)    |
| `splash.png`          | 1242×2688 | Splash screen (logo no off-white)|
| `favicon.png`         | 64×64     | Favicon web                      |

## Estrutura de pastas

```
mobile/assets/tenfy/
  logos/          - Logo Tenfy horizontal, vertical, símbolo, variações
  app-icons/      - Ícones de app em diferentes modos (crops de referência)
  favicons/       - Favicon de referência
  ui-icons/       - Ícones de interface (home, calendar, search, filter, etc.)
  badges/         - Badges de torneio (grid, needs manual separation)
  stickers/       - Stickers ilustrativos (shield, trophy, lightning, racket...)
  illustrations/  - Ilustrações (onboarding, empty state, loading)
  images/         - Imagens (hero, card promo, template post, photography)
  misc/           - Avatares, padrão decorativo, launcher icon, notification icon
```

## Total de arquivos: 66

## Logos prontos para uso no app

| Arquivo                              | Uso recomendado              |
|--------------------------------------|------------------------------|
| `logos/logo-main-clean.png`          | Auth screens, header          |
| `logos/logo-horizontal-clean.png`    | Header compacto               |
| `logos/logo-vertical-clean.png`      | Onboarding                   |
| `logos/logo-symbol-clean.png`        | Ícone pequeno, avatar         |
| `logos/logo-mono-dark-clean.png`     | Fundo claro, mono            |
| `logos/logo-mono-light-clean.png`    | Fundo escuro, mono           |

## Ícones de UI disponíveis

Extraídos da grid de ícones do produto (separação automática):
- `ui-icons/icon-home.png`
- `ui-icons/icon-calendar.png`
- `ui-icons/icon-search.png`
- `ui-icons/icon-filter.png`
- `ui-icons/icon-favorites.png`
- `ui-icons/icon-profile.png`
- `ui-icons/icon-ranking.png`
- `ui-icons/icon-star.png`
- `ui-icons/icon-settings.png`
- `ui-icons/icon-tennis.png`

> **Nota:** Os ícones de UI foram extraídos automaticamente de um grid. Podem precisar de revisão manual para verificar precisão de cada posição.

## Assets que precisam de revisão manual

| Asset                          | Motivo                                         |
|--------------------------------|------------------------------------------------|
| `badges/badges-mode-raw.png`   | Grid com múltiplos badges juntos               |
| `badges/badges-system-raw.png` | Grid com badges do sistema visual              |
| `ui-icons/ui-icons-grid-raw.png` | Grid completo para referência                |
| `misc/avatar-circular-raw.png` | Contém label do documento                     |
| `misc/avatar-square-raw.png`   | Contém label do documento                     |
| Stickers individuais           | Coordenadas estimadas — verificar cada um      |

## Como usar no app mobile

```tsx
// Logo na tela de login
import { Image } from 'react-native';
<Image
  source={require('../assets/tenfy/logos/logo-main-clean.png')}
  style={{ width: 200, height: 60 }}
  resizeMode="contain"
/>

// Ícone de UI
<Image
  source={require('../assets/tenfy/ui-icons/icon-home.png')}
  style={{ width: 24, height: 24 }}
/>
```

## Fontes da extração

| Arquivo de design                         | Assets extraídos                |
|-------------------------------------------|---------------------------------|
| `Logo e variações.png`                    | Logos e variações               |
| `Ícones e variações.png`                  | App icons, UI icons, badges     |
| `Imagens e elementos visuais.png`         | Ilustrações, stickers, imagens  |
| `Manual da marca - Sistema Visual.png`    | Badges do sistema visual        |
