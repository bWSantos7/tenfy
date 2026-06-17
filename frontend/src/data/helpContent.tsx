import {
  LucideIcon, Home, Calendar, Star, Award, User, Users, Bell, CreditCard,
  ClipboardList, Trophy, UserPlus, Repeat, Settings, HelpCircle, Sparkles,
} from 'lucide-react';
import { Role } from '../types';

// ─── Tipos ───────────────────────────────────────────────────────────────────

export interface TutorialStep {
  icon: LucideIcon;
  title: string;
  body: string;
  /** Onde encontrar na interface (dica curta de localização). */
  hint?: string;
}

export interface HelpTopic {
  id: string;
  icon: LucideIcon;
  title: string;
  /** O que é a funcionalidade. */
  what: string;
  /** Como funciona / como usar. */
  how: string;
  /** Em quais situações usar. */
  when: string;
  keywords?: string[];
  /** Se ausente, vale para todos os perfis. */
  roles?: Role[];
}

const isParent = (role?: Role) => role === 'parent';

// ─── Tutorial de primeiro acesso (passo a passo, adaptado por perfil) ──────────

export function getTutorialSteps(role?: Role): TutorialStep[] {
  const parent = isParent(role);

  const intro: TutorialStep = {
    icon: Sparkles,
    title: parent ? 'Bem-vindo(a) ao Tenfy!' : 'Bem-vindo(a) ao Tenfy!',
    body: parent
      ? 'Aqui você acompanha a vida esportiva dos seus dependentes: torneios compatíveis, agenda, inscrições, rankings e resultados. Vamos te mostrar o básico em poucos passos.'
      : 'Aqui você acompanha torneios compatíveis com seu perfil, sua agenda, inscrições, rankings e resultados. Vamos te mostrar o básico em poucos passos.',
  };

  const parentOnly: TutorialStep[] = [
    {
      icon: UserPlus,
      title: 'Cadastre um dependente',
      body: 'Adicione o perfil do seu filho(a) ou atleta para acompanhar tudo por ele. Você pode criar o perfil esportivo e convidar dependentes que já têm conta.',
      hint: 'Configurações da conta → seção "Meus dependentes".',
    },
    {
      icon: Repeat,
      title: 'Alterne entre dependentes',
      body: 'Tem mais de um dependente? Use o seletor de perfil no topo da tela Início para trocar qual atleta você está acompanhando. Torneios, agenda e elegibilidade se ajustam ao perfil ativo.',
      hint: 'Tela Início → seletor de perfil no topo.',
    },
  ];

  const common: TutorialStep[] = [
    {
      icon: Calendar,
      title: 'Torneios compatíveis',
      body: parent
        ? 'Na aba Torneios você vê os campeonatos e filtra por aqueles compatíveis com a categoria, idade e região do dependente ativo.'
        : 'Na aba Torneios você vê os campeonatos e filtra por aqueles compatíveis com sua categoria, idade e região.',
      hint: 'Barra de navegação → Torneios.',
    },
    {
      icon: Star,
      title: 'Acompanhe torneios',
      body: 'Encontrou um torneio interessante? Toque na estrela para favoritá-lo. Ele entra na sua Agenda e você passa a receber alertas de prazos e mudanças.',
      hint: 'Em qualquer torneio → ícone de estrela.',
    },
    {
      icon: Star,
      title: 'Sua Agenda',
      body: 'A aba Agenda reúne os torneios que você acompanha, com datas e status. É o seu calendário pessoal dentro do Tenfy.',
      hint: 'Barra de navegação → Agenda.',
    },
    {
      icon: ClipboardList,
      title: 'Inscrições',
      body: parent
        ? 'Veja em quais torneios o dependente aparece inscrito, com status de pagamento e posição na chave quando a federação publica a lista.'
        : 'Veja em quais torneios você aparece inscrito, com status de pagamento e posição na chave quando a federação publica a lista.',
      hint: 'Tela Início → "Inscrições", ou abra um torneio para ver os inscritos.',
    },
    {
      icon: Trophy,
      title: 'Rankings e resultados',
      body: 'Na aba Resultados você acompanha rankings, classificações e resultados de partidas, quando a fonte oficial disponibiliza.',
      hint: 'Barra de navegação → Resultados.',
    },
    {
      icon: User,
      title: 'Perfil esportivo',
      body: parent
        ? 'Em Perfil você consulta e atualiza os dados esportivos do dependente: categoria, federação, modalidade e mão dominante. Eles definem a compatibilidade com os torneios.'
        : 'Em Perfil você consulta e atualiza seus dados esportivos: categoria, federação, modalidade e mão dominante. Eles definem a compatibilidade com os torneios.',
      hint: 'Barra de navegação → Perfil.',
    },
    {
      icon: Settings,
      title: 'Configurações da conta',
      body: parent
        ? 'Em Configurações você ajusta seus dados, gerencia dependentes, preferências de alertas e sua assinatura.'
        : 'Em Configurações você ajusta seus dados, preferências de alertas e sua assinatura.',
      hint: 'Perfil → Configurações da conta.',
    },
    {
      icon: HelpCircle,
      title: 'Precisa de ajuda?',
      body: 'A qualquer momento, toque no ícone de interrogação (?) no canto superior direito para abrir a Ajuda, com explicações de cada funcionalidade e uma busca por palavra-chave.',
      hint: 'Canto superior direito → ícone "?".',
    },
  ];

  return [intro, ...(parent ? parentOnly : []), ...common];
}

// ─── Página de Ajuda (tópicos por funcionalidade) ─────────────────────────────

export const HELP_TOPICS: HelpTopic[] = [
  {
    id: 'dependentes',
    icon: UserPlus,
    title: 'Cadastro de dependentes',
    what: 'Permite que um responsável acompanhe e gerencie o perfil esportivo de um ou mais dependentes (filhos ou atletas).',
    how: 'Vá em Configurações da conta → seção "Meus dependentes". Você pode criar o perfil esportivo do dependente ou convidar alguém que já tenha conta. Para acompanhar um dependente específico, use o seletor de perfil no topo da tela Início.',
    when: 'Use quando você é pai, mãe ou responsável e quer acompanhar torneios, agenda e resultados em nome do dependente.',
    keywords: ['filho', 'responsável', 'pai', 'mãe', 'convite', 'vínculo', 'criança', 'menor'],
    roles: ['parent'],
  },
  {
    id: 'perfil-esportivo',
    icon: User,
    title: 'Perfil esportivo',
    what: 'Reúne os dados esportivos do jogador: categoria, federação, modalidade, mão dominante, cidade e nível competitivo.',
    how: 'Acesse a aba Perfil. Mantenha os dados atualizados — eles definem quais torneios aparecem como compatíveis e ajudam na análise de elegibilidade.',
    when: 'Atualize sempre que mudar de categoria, federação ou cidade, ou ao começar a usar o app.',
    keywords: ['categoria', 'federação', 'modalidade', 'mão dominante', 'idade', 'nível', 'jogador'],
  },
  {
    id: 'torneios',
    icon: Calendar,
    title: 'Torneios compatíveis',
    what: 'Lista consolidada de torneios, com indicação dos que combinam com o perfil (categoria, idade, modalidade e região).',
    how: 'Abra a aba Torneios. Use os filtros para refinar por modalidade, data, região e compatibilidade. Toque em um torneio para ver detalhes, categorias, prazos e inscritos.',
    when: 'Use para descobrir onde competir e avaliar se o perfil é elegível para cada categoria.',
    keywords: ['campeonato', 'compatível', 'elegibilidade', 'filtro', 'calendário', 'competir'],
  },
  {
    id: 'agenda',
    icon: Star,
    title: 'Agenda',
    what: 'Seu calendário pessoal com os torneios que você escolheu acompanhar.',
    how: 'Toque na estrela em qualquer torneio para adicioná-lo à Agenda. Depois acesse a aba Agenda para ver datas, status e gerenciar os alertas de cada torneio.',
    when: 'Use para não perder prazos e organizar a temporada de competições.',
    keywords: ['favoritos', 'acompanhar', 'watchlist', 'calendário', 'estrela'],
  },
  {
    id: 'inscricoes',
    icon: ClipboardList,
    title: 'Inscrições',
    what: 'Mostra em quais torneios o jogador aparece inscrito, com status de pagamento e posição na chave.',
    how: 'Acesse "Inscrições" pela tela Início ou abra um torneio para ver a lista de inscritos publicada pela federação. Quando a fonte oficial disponibiliza, o Tenfy associa automaticamente a inscrição ao perfil.',
    when: 'Use para confirmar se a inscrição foi registrada pela federação e acompanhar o status.',
    keywords: ['inscrito', 'inscrição', 'chave', 'pagamento', 'federação', 'lista'],
  },
  {
    id: 'rankings',
    icon: Trophy,
    title: 'Rankings',
    what: 'Exibe rankings e classificações do jogador conforme publicado pelas fontes oficiais (federações / Tênis Integrado).',
    how: 'Acesse a aba Resultados para ver os rankings vinculados ao perfil. Os dados aparecem quando a fonte oficial os disponibiliza.',
    when: 'Use para acompanhar a evolução e a posição do jogador nas categorias em que compete.',
    keywords: ['classificação', 'posição', 'pontos', 'ranking', 'utr'],
  },
  {
    id: 'resultados',
    icon: Award,
    title: 'Resultados',
    what: 'Histórico de resultados de partidas e torneios disputados.',
    how: 'Acesse a aba Resultados. Os resultados são exibidos conforme a fonte oficial publica; alguns dados podem aparecer como "não informado" quando a fonte não os fornece.',
    when: 'Use para revisar desempenho recente e o histórico de competições.',
    keywords: ['resultado', 'partida', 'vitória', 'derrota', 'histórico', 'desempenho'],
  },
  {
    id: 'alertas',
    icon: Bell,
    title: 'Alertas e notificações',
    what: 'Avisos sobre prazos de inscrição, mudanças em torneios e publicação de chaves dos torneios que você acompanha.',
    how: 'Toque no sino no topo da tela para ver os alertas. Nas configurações você define quais notificações deseja receber (no app e push).',
    when: 'Use para ser avisado a tempo de prazos e novidades dos torneios da sua Agenda.',
    keywords: ['notificação', 'sino', 'aviso', 'prazo', 'push', 'lembrete'],
  },
  {
    id: 'configuracoes',
    icon: Settings,
    title: 'Configurações da conta',
    what: 'Onde você ajusta seus dados pessoais, preferências de alertas, dependentes (responsável) e a conta.',
    how: 'Acesse pela aba Perfil → "Configurações da conta". Lá você edita nome, telefone, preferências e, se for responsável, gerencia dependentes.',
    when: 'Use para manter seus dados em dia e personalizar a experiência.',
    keywords: ['conta', 'dados', 'preferências', 'editar', 'configuração', 'senha'],
  },
  {
    id: 'assinatura',
    icon: CreditCard,
    title: 'Assinatura e plano',
    what: 'Gerenciamento do seu plano (Individual ou Família) e da forma de pagamento.',
    how: 'Acesse "Assinatura" para ver seu plano atual, escolher um plano e pagar via Pix (QR code no app) ou cartão. Com plano pago pendente, o acesso fica bloqueado até a confirmação do pagamento.',
    when: 'Use para assinar, trocar de plano ou regularizar um pagamento pendente.',
    keywords: ['plano', 'pagamento', 'pix', 'cartão', 'individual', 'família', 'cupom', 'assinar'],
  },
  {
    id: 'faq',
    icon: HelpCircle,
    title: 'Dúvidas frequentes',
    what: 'Respostas rápidas para as perguntas mais comuns.',
    how: 'Por que um torneio não aparece como compatível? Verifique se o perfil esportivo (categoria, federação e idade) está completo e atualizado. • Por que minha inscrição não aparece? O Tenfy depende da lista publicada pela federação; se ela ainda não publicou, a inscrição pode não estar disponível. • Como volto a ver o tutorial? Toque em "Rever tutorial" nesta página de Ajuda.',
    when: 'Consulte antes de procurar suporte — a maioria das dúvidas é resolvida aqui.',
    keywords: ['dúvida', 'faq', 'pergunta', 'problema', 'ajuda', 'suporte', 'tutorial'],
  },
];

/** Tópicos de ajuda visíveis para o perfil informado. */
export function getHelpTopics(role?: Role): HelpTopic[] {
  return HELP_TOPICS.filter((t) => !t.roles || (role && t.roles.includes(role)));
}
