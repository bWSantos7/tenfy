# Metadados para o App Store Connect — Tenfy iOS

Texto pronto para colar no App Store Connect (ASC) quando a conta Apple estiver ativa.
Idioma primário: **Português (Brasil)**. Limites de caracteres da Apple anotados em cada campo.

---

## Informações do app

**Nome (Name)** — máx. 30 caracteres
```
Tenfy
```

**Subtítulo (Subtitle)** — máx. 30 caracteres
```
Torneios de tênis e agenda
```

**Categoria**
- Primária: **Esportes (Sports)**
- Secundária (opcional): Estilo de vida (Lifestyle)

**Texto promocional (Promotional Text)** — máx. 170 caracteres (pode ser atualizado sem nova versão)
```
Acompanhe torneios de tênis compatíveis com seu perfil, monte sua agenda e receba alertas de prazos, chaves e resultados. Tudo em um só lugar.
```

---

## Descrição (Description) — máx. 4000 caracteres

```
O Tenfy reúne, em um só app, os torneios de tênis das principais federações e
confederações — e mostra quais combinam com o seu perfil esportivo.

PARA QUEM É
• Jogadores que querem acompanhar e planejar seus torneios.
• Pais e responsáveis que acompanham a vida esportiva dos filhos.
• Treinadores que acompanham seus alunos.

O QUE VOCÊ FAZ NO TENFY
• Calendário consolidado: veja torneios de várias fontes em um só lugar, por mês.
• Compatibilidade: filtre pelos torneios certos para sua categoria, idade e região.
• Agenda pessoal: favorite torneios e acompanhe datas e status.
• Alertas: receba avisos de prazos de inscrição, mudanças e publicação de chaves.
• Inscrições: veja em quais torneios você aparece inscrito, com status quando a
  federação publica a lista.
• Rankings e resultados: acompanhe classificações e resultados quando a fonte oficial
  disponibiliza.
• Perfil esportivo: categoria, federação, modalidade, mão dominante e seu rating UTR.
• Responsável e dependentes: gerencie vários perfis com isolamento de dados.

DADOS REAIS E RASTREÁVEIS
As informações vêm de fontes públicas e oficiais, sempre com a origem registrada.
Quando uma informação não está disponível, o app deixa isso claro — sem inventar dados.

ASSINATURA
A criação de conta e a assinatura são feitas no site tenfy.com.br. No app, você acessa
sua conta já existente e acompanha tudo.

Tênis a sério, do jeito que você acompanha de verdade.
```

---

## Palavras-chave (Keywords) — máx. 100 caracteres, separadas por vírgula (sem espaços)

```
tênis,torneio,tenista,CBT,FPT,ranking,UTR,inscrição,agenda,quadra,campeonato,esporte
```

---

## URLs

| Campo | Valor |
|---|---|
| **Support URL** | `https://tenfy.com.br` |
| **Marketing URL** (opcional) | `https://tenfy.com.br` |
| **Privacy Policy URL** (obrigatório) | `https://tenfy.com.br/politica-privacidade` |

---

## App Review Information (notas para o revisor)

**Sign-In required:** Sim. Fornecer a conta de demonstração abaixo.

**Conta de demonstração** (criar uma conta real com assinatura ativa antes de enviar):
```
Usuário: <e-mail de teste>
Senha:   <senha de teste>
```

**Notes (cole no campo "Notes"):**
```
O Tenfy é um app de acompanhamento de torneios de tênis (serviço multiplataforma,
Guideline 3.1.3(b)). A criação de conta e a assinatura são realizadas no site
(tenfy.com.br); o aplicativo opera com login de contas já existentes e não vende
conteúdo digital dentro do app.

A conta de teste informada acima tem acesso ativo para avaliação de todas as telas
(torneios, agenda, inscrições, resultados, perfil e alertas).

Permissões: câmera e biblioteca de fotos são usadas apenas para a foto de perfil;
notificações são opcionais (alertas de prazos/mudanças de torneios). O app não realiza
rastreamento de usuários nem usa IDFA.
```

---

## App Privacy ("nutrition labels") — o que declarar no ASC

Marque **"Data is collected"** e declare:

| Tipo de dado | Categoria ASC | Usado para | Vinculado à identidade? | Rastreamento? |
|---|---|---|---|---|
| E-mail | Contact Info → Email Address | Funcionalidade do app | Sim | Não |
| Nome | Contact Info → Name | Funcionalidade do app | Sim | Não |
| Telefone | Contact Info → Phone Number | Funcionalidade do app | Sim | Não |
| CPF | Identifiers → Other (national ID) | Funcionalidade do app / pagamentos | Sim | Não |
| Foto de perfil | User Content → Photos or Videos | Funcionalidade do app | Sim | Não |
| Torneios seguidos / uso | Usage Data → Product Interaction | Funcionalidade do app | Sim | Não |

- **Tracking:** **Nenhum** (não usar ATT / `NSUserTrackingUsageDescription`).
- **Atenção a menores/dependentes:** declarar a coleta, mas **não** marcar Kids Category.

---

## Age Rating

Responder o questionário sem conteúdo sensível → resultado esperado **4+**.

---

## Versão / Build

- **Version:** `1.0.10` (acompanha o `app.json`)
- **Build number:** gerado automaticamente (`autoIncrement` no perfil de produção do EAS)

---

## Assets visuais a preparar

- [ ] **Ícone da loja** 1024×1024 sem alpha (já temos: `mobile/assets/icon-ios.png`).
- [ ] **Screenshots iPhone 6.7"** (obrigatório) — ex.: 1290×2796. Sugestão de telas:
      Início, Torneios (lista por mês), Detalhe de torneio, Agenda, Perfil (com UTR).
- iPad não é necessário (`supportsTablet: false`).
