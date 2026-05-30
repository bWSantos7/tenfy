import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import {
  Calendar,
  ChevronRight,
  Clock,
  MapPin,
  Menu,
  Moon,
  Search,
  Sparkles,
  Star,
  Sun,
  User,
  Users,
  CheckCircle2,
  ArrowRight,
  Smartphone,
  X,
  Award,
  BookOpen,
  Filter,
  Check
} from 'lucide-react';

// Simulated Tournament Data for the Interactive Widget
interface MockTournament {
  id: number;
  title: string;
  federation: string;
  state: string;
  location: string;
  startDate: string;
  endDate: string;
  closingDate: string;
  classes: string[];
}

const MOCK_TOURNAMENTS: MockTournament[] = [
  {
    id: 1,
    title: 'Campeonato Paulista de Classes - Etapa Pinheiros',
    federation: 'FPT',
    state: 'SP',
    location: 'Esporte Clube Pinheiros, São Paulo',
    startDate: '25/06/2026',
    endDate: '28/06/2026',
    closingDate: '18/06/2026',
    classes: ['1ª Classe', '2ª Classe', '3ª Classe', '4ª Classe'],
  },
  {
    id: 2,
    title: 'Copa Rio de Tênis - Barra da Tijuca',
    federation: 'FTERJ',
    state: 'RJ',
    location: 'Novo Rio Country Club, Rio de Janeiro',
    startDate: '02/07/2026',
    endDate: '05/07/2026',
    closingDate: '24/06/2026',
    classes: ['3ª Classe', '4ª Classe', 'Iniciante'],
  },
  {
    id: 4,
    title: 'Copa Minas Tênis Clube de Classes',
    federation: 'FMT',
    state: 'MG',
    location: 'Minas Tênis Clube, Belo Horizonte',
    startDate: '18/07/2026',
    endDate: '21/07/2026',
    closingDate: '10/07/2026',
    classes: ['2ª Classe', '3ª Classe', '4ª Classe', 'Iniciante'],
  },
  {
    id: 5,
    title: 'Copa Sul de Tênis - Etapa Porto Alegre',
    federation: 'FGT',
    state: 'RS',
    location: 'Associação Leopoldina Juvenil, Porto Alegre',
    startDate: '25/07/2026',
    endDate: '28/07/2026',
    closingDate: '16/07/2026',
    classes: ['1ª Classe', '2ª Classe', '3ª Classe', '4ª Classe', 'Iniciante'],
  },
];

export const LandingPage: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const { theme, toggle: toggleTheme } = useTheme();
  
  // States
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'athletes' | 'parents' | 'organizers'>('athletes');
  
  // Simulator Widget States
  const [selectedState, setSelectedState] = useState<string>('Todos');
  const [selectedClass, setSelectedClass] = useState<string>('Todas');
  
  // Filter mock tournaments based on simulator options
  const filteredTournaments = MOCK_TOURNAMENTS.filter((t) => {
    const matchState = selectedState === 'Todos' || t.state === selectedState;
    const matchClass = selectedClass === 'Todas' || t.classes.includes(selectedClass);
    return matchState && matchClass;
  });

  return (
    <div className="min-h-screen bg-gradient-to-b from-bg-subtle via-bg-base to-bg-subtle text-text-primary overflow-x-hidden">
      
      {/* ─── NAVBAR ──────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 w-full bg-bg-card/75 backdrop-blur-md border-b border-border-subtle transition-all duration-300">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          
          {/* Logo */}
          <Link to={isAuthenticated ? '/inicio' : '/'} className="flex items-center group">
            <img src="/logos/logo_clara.png" alt="Tenfy" className="h-9 max-w-[40px] object-contain transition-transform duration-300 group-hover:scale-105 dark:hidden" />
            <img src="/logos/logo_escura.png" alt="Tenfy" className="h-9 max-w-[40px] object-contain transition-transform duration-300 group-hover:scale-105 hidden dark:block" />
          </Link>
          
          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center gap-6 text-sm font-medium">
            <a href="#recursos" className="text-text-secondary hover:text-accent-neon transition-colors">Recursos</a>
            <a href="#beneficios" className="text-text-secondary hover:text-accent-neon transition-colors">Benefícios</a>
            <a href="#como-funciona" className="text-text-secondary hover:text-accent-neon transition-colors">Como Funciona</a>
            <a href="#simulador" className="text-text-secondary hover:text-accent-neon transition-colors">Simulador</a>
            <a href="#galeria" className="text-text-secondary hover:text-accent-neon transition-colors">Galeria</a>
          </nav>
          
          {/* Action Buttons & Theme Toggle */}
          <div className="hidden md:flex items-center gap-3">
            <button 
              onClick={toggleTheme} 
              className="p-2 rounded-xl bg-bg-elevated/50 text-text-secondary hover:text-accent-neon transition-all hover:bg-bg-elevated"
              title={theme === 'dark' ? 'Modo claro' : 'Modo escuro'}
            >
              {theme === 'dark' ? <Sun className="w-4 h-4 text-accent-neon" /> : <Moon className="w-4 h-4" />}
            </button>
            
            {isAuthenticated ? (
              <Link to="/inicio" className="btn-primary flex items-center gap-2 !py-2 !px-4 text-sm">
                Ir para o Painel <ArrowRight className="w-4 h-4" />
              </Link>
            ) : (
              <>
                <Link to="/login" className="btn-secondary !py-2 !px-4 text-sm font-semibold">
                  Entrar
                </Link>
                <Link to="/register" className="btn-primary !py-2 !px-4 text-sm">
                  Começar Grátis
                </Link>
              </>
            )}
          </div>
          
          {/* Mobile Right Controls (Menu & Theme toggle) */}
          <div className="flex md:hidden items-center gap-2">
            <button 
              onClick={toggleTheme} 
              className="p-2 rounded-lg bg-bg-elevated/50 text-text-secondary transition-colors"
            >
              {theme === 'dark' ? <Sun className="w-4 h-4 text-accent-neon" /> : <Moon className="w-4 h-4" />}
            </button>
            <button 
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-lg bg-bg-elevated/50 text-text-secondary transition-colors"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
          
        </div>
        
        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-border-subtle bg-bg-card px-4 py-6 space-y-4 animate-fade-in shadow-xl">
            <div className="flex flex-col gap-3 font-medium">
              <a 
                href="#recursos" 
                onClick={() => setMobileMenuOpen(false)}
                className="text-text-secondary py-2 border-b border-border-subtle/40 hover:text-accent-neon"
              >
                Recursos
              </a>
              <a 
                href="#beneficios" 
                onClick={() => setMobileMenuOpen(false)}
                className="text-text-secondary py-2 border-b border-border-subtle/40 hover:text-accent-neon"
              >
                Benefícios
              </a>
              <a 
                href="#como-funciona" 
                onClick={() => setMobileMenuOpen(false)}
                className="text-text-secondary py-2 border-b border-border-subtle/40 hover:text-accent-neon"
              >
                Como Funciona
              </a>
              <a 
                href="#simulador" 
                onClick={() => setMobileMenuOpen(false)}
                className="text-text-secondary py-2 border-b border-border-subtle/40 hover:text-accent-neon"
              >
                Simulador
              </a>
              <a 
                href="#galeria" 
                onClick={() => setMobileMenuOpen(false)}
                className="text-text-secondary py-2 border-b border-border-subtle/40 hover:text-accent-neon"
              >
                Galeria
              </a>
            </div>
            
            <div className="flex flex-col gap-2 pt-2">
              {isAuthenticated ? (
                <Link 
                  to="/inicio" 
                  onClick={() => setMobileMenuOpen(false)}
                  className="btn-primary w-full text-center flex items-center justify-center gap-2"
                >
                  Ir para o Painel <ArrowRight className="w-4 h-4" />
                </Link>
              ) : (
                <>
                  <Link 
                    to="/login" 
                    onClick={() => setMobileMenuOpen(false)}
                    className="btn-secondary w-full text-center"
                  >
                    Entrar
                  </Link>
                  <Link 
                    to="/register" 
                    onClick={() => setMobileMenuOpen(false)}
                    className="btn-primary w-full text-center"
                  >
                    Começar Grátis
                  </Link>
                </>
              )}
            </div>
          </div>
        )}
      </header>

      {/* ─── HERO SECTION ─────────────────────────────────────────────────── */}
      <section className="relative py-12 md:py-24 px-4 overflow-hidden">
        {/* Neon blur background circles */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[350px] md:w-[600px] h-[350px] md:h-[600px] bg-accent-neon/10 rounded-full blur-[100px] pointer-events-none z-0" />
        
        <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-12 items-center relative z-10">
          
          {/* Left Hero Texts */}
          <div className="lg:col-span-7 flex flex-col items-start text-left space-y-6">
            
            {/* Tag/Badge */}
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent-neon/10 border border-accent-neon/30 text-xs font-semibold text-accent-neon animate-pulse">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Calendário Inteligente de Tênis</span>
            </div>
            
            <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight leading-tight">
              Seu jogo.<br/>
              <span className="bg-gradient-to-r from-accent-neon to-accent-blue bg-clip-text text-transparent drop-shadow-glow">
                Sua agenda.
              </span><br/>
              Simplificados.
            </h1>
            
            <p className="text-base md:text-lg text-text-secondary max-w-xl leading-relaxed">
              O <strong className="text-text-primary">Tenfy</strong> é a plataforma definitiva que centraliza torneios das federações brasileiras, analisa sua elegibilidade esportiva automaticamente e organiza seu calendário para você focar no que importa: <span className="text-accent-neon font-semibold">evoluir nas quadras.</span>
            </p>
            
            {/* CTA Actions */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4 w-full sm:w-auto">
              <Link to={isAuthenticated ? "/inicio" : "/register"} className="btn-primary text-center flex items-center justify-center gap-2 shadow-glow hover:scale-105 transition-transform duration-300">
                Criar Conta Grátis
                <ArrowRight className="w-4 h-4" />
              </Link>
              <a href="#simulador" className="btn-secondary text-center flex items-center justify-center gap-2 hover:bg-bg-elevated hover:scale-105 transition-transform duration-300">
                Testar Simulador
              </a>
            </div>
            
            {/* Key benefits list */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 pt-4 text-xs font-medium text-text-muted w-full border-t border-border-subtle/50">
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-accent-neon shrink-0" />
                <span>Compatibilidade Inteligente</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-accent-neon shrink-0" />
                <span>Alertas de Inscrições</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-accent-neon shrink-0" />
                <span>Experiência Web & Mobile</span>
              </div>
            </div>
            
          </div>
          
          {/* Right Hero Image / Visual Frame */}
          <div className="lg:col-span-5 relative flex justify-center items-center">
            <div className="relative w-full max-w-sm md:max-w-md aspect-square rounded-3xl bg-gradient-to-tr from-accent-neon/10 to-accent-blue/10 p-1 border border-border-subtle shadow-card-dark overflow-hidden group">
              <div className="absolute inset-0 bg-bg-card/80 backdrop-blur-2xl rounded-3xl" />
              
              {/* Floating elements to give a "live" UI feel */}
              <div className="relative w-full h-full flex flex-col justify-center items-center p-6 space-y-6">
                
                {/* Brand Logo showcase */}
                <div className="bg-bg-elevated/70 border border-border-subtle p-6 rounded-2xl shadow-card w-full max-w-[280px] transform hover:-translate-y-2 transition-transform duration-300">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] uppercase font-bold tracking-widest text-accent-neon">Identidade Visual</span>
                    <span className="w-2.5 h-2.5 rounded-full bg-accent-neon animate-ping" />
                  </div>
                  <img src="/logos/logo_clara.png" alt="Tenfy" className="w-full object-contain dark:hidden" />
                  <img src="/logos/logo_escura.png" alt="Tenfy" className="w-full object-contain hidden dark:block" />
                  <div className="mt-4 flex items-center justify-between text-xs text-text-muted font-medium border-t border-border-subtle/50 pt-3">
                    <span>Branding Original</span>
                    <span>v1.0.0</span>
                  </div>
                </div>

                {/* Simulated Floating App Card */}
                <div className="bg-bg-elevated/80 border border-accent-neon/30 p-5 rounded-2xl shadow-glow w-full max-w-[280px] self-end -mr-4 md:-mr-8 transform rotate-3 hover:rotate-0 hover:scale-105 transition-all duration-300">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-8 h-8 rounded-lg bg-accent-neon flex items-center justify-center shadow-glow text-bg-base font-extrabold text-sm">T</div>
                    <div>
                      <h4 className="text-xs font-bold">App Tenfy</h4>
                      <p className="text-[10px] text-text-muted">Compatibilidade Atleta</p>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="h-2 w-full bg-bg-base rounded-full overflow-hidden">
                      <div className="h-full bg-accent-neon w-[94%]" />
                    </div>
                    <div className="flex justify-between text-[10px] font-bold">
                      <span className="text-accent-neon">94% Elegível</span>
                      <span className="text-text-secondary">São Paulo</span>
                    </div>
                  </div>
                </div>

              </div>
            </div>
            
            {/* Background geometric design grids */}
            <div className="absolute -bottom-6 -left-6 w-24 h-24 bg-accent-blue/10 rounded-full blur-2xl pointer-events-none" />
            <div className="absolute -top-6 -right-6 w-24 h-24 bg-accent-neon/20 rounded-full blur-2xl pointer-events-none" />
          </div>
          
        </div>
      </section>

      {/* ─── FEATURES PRESENTATION (APRESENTAÇÃO DO TENFY) ────────────────── */}
      <section id="recursos" className="py-20 bg-bg-card/40 border-y border-border-subtle px-4 relative">
        <div className="max-w-6xl mx-auto space-y-12">
          
          <div className="text-center max-w-2xl mx-auto space-y-4">
            <h2 className="text-xs uppercase font-extrabold tracking-widest text-accent-neon">Tecnologia & Praticidade</h2>
            <h3 className="text-3xl md:text-4xl font-bold">O que faz o Tenfy ser incomparável?</h3>
            <p className="text-text-secondary text-sm md:text-base leading-relaxed">
              Desenvolvemos um sistema inteligente com ferramentas exclusivas que resolvem a frustração de buscar torneios em portais obsoletos e decifrar regras burocráticas.
            </p>
          </div>
          
          {/* Features Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            
            {/* Feature 1 */}
            <div className="card hover:-translate-y-2 transition-all duration-300 flex flex-col justify-between group hover:border-accent-neon/40">
              <div className="space-y-4">
                <div className="w-12 h-12 rounded-xl bg-accent-neon/10 border border-accent-neon/30 flex items-center justify-center text-accent-neon group-hover:scale-110 transition-transform duration-300">
                  <Search className="w-6 h-6" />
                </div>
                <h4 className="text-lg font-bold">Agregador de Torneios</h4>
                <p className="text-xs md:text-sm text-text-secondary leading-relaxed">
                  Buscamos e catalogamos automaticamente torneios das maiores federações e ligas de tênis. Tudo integrado em um feed unificado e atualizado em tempo real.
                </p>
              </div>
              <div className="mt-6 pt-4 border-t border-border-subtle/50 text-xs font-semibold text-accent-neon flex items-center gap-1">
                <span>Federações Integradas</span>
                <ChevronRight className="w-3 h-3" />
              </div>
            </div>
            
            {/* Feature 2 */}
            <div className="card hover:-translate-y-2 transition-all duration-300 flex flex-col justify-between group hover:border-accent-neon/40">
              <div className="space-y-4">
                <div className="w-12 h-12 rounded-xl bg-accent-neon/10 border border-accent-neon/30 flex items-center justify-center text-accent-neon group-hover:scale-110 transition-transform duration-300">
                  <Sparkles className="w-6 h-6" />
                </div>
                <h4 className="text-lg font-bold">Análise de Compatibilidade</h4>
                <p className="text-xs md:text-sm text-text-secondary leading-relaxed">
                  Nosso algoritmo exclusivo lê sua idade, gênero, nível técnico e classe esportiva para indicar exatamente em quais categorias e torneios você pode se inscrever.
                </p>
              </div>
              <div className="mt-6 pt-4 border-t border-border-subtle/50 text-xs font-semibold text-accent-neon flex items-center gap-1">
                <span>Evite Desclassificações</span>
                <ChevronRight className="w-3 h-3" />
              </div>
            </div>
            
            {/* Feature 3 */}
            <div className="card hover:-translate-y-2 transition-all duration-300 flex flex-col justify-between group hover:border-accent-neon/40">
              <div className="space-y-4">
                <div className="w-12 h-12 rounded-xl bg-accent-neon/10 border border-accent-neon/30 flex items-center justify-center text-accent-neon group-hover:scale-110 transition-transform duration-300">
                  <Clock className="w-6 h-6" />
                </div>
                <h4 className="text-lg font-bold">Prazo Sob Controle</h4>
                <p className="text-xs md:text-sm text-text-secondary leading-relaxed">
                  Favorite torneios na sua Agenda Personalizada e receba alertas automáticos de fechamento de inscrição, chaves geradas e horários de jogos.
                </p>
              </div>
              <div className="mt-6 pt-4 border-t border-border-subtle/50 text-xs font-semibold text-accent-neon flex items-center gap-1">
                <span>Garanta sua Inscrição</span>
                <ChevronRight className="w-3 h-3" />
              </div>
            </div>
            
          </div>
          
        </div>
      </section>

      {/* ─── ROLE-BASED BENEFITS (BENEFÍCIOS PARA ATORES) ────────────────── */}
      <section id="beneficios" className="py-20 px-4 max-w-6xl mx-auto space-y-12">
        
        <div className="text-center max-w-2xl mx-auto space-y-4">
          <h2 className="text-xs uppercase font-extrabold tracking-widest text-accent-blue">Perfis Personalizados</h2>
          <h3 className="text-3xl md:text-4xl font-bold">Desenhado para todos os lados do esporte</h3>
          <p className="text-text-secondary text-sm md:text-base">
            O tênis é um ecossistema. Seja você o jogador focado, o pai apoiador ou o organizador/treinador, o Tenfy tem a ferramenta perfeita.
          </p>
        </div>
        
        {/* Navigation Tabs */}
        <div className="flex justify-center border-b border-border-subtle max-w-md mx-auto p-1 bg-bg-card rounded-2xl shadow-card">
          <button
            onClick={() => setActiveTab('athletes')}
            className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition-all ${
              activeTab === 'athletes' 
                ? 'bg-accent-neon text-bg-base shadow-glow' 
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            <User className="w-4 h-4" />
            Atletas
          </button>
          
          <button
            onClick={() => setActiveTab('parents')}
            className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition-all ${
              activeTab === 'parents' 
                ? 'bg-accent-neon text-bg-base shadow-glow' 
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            <Users className="w-4 h-4" />
            Pais
          </button>
          
          <button
            onClick={() => setActiveTab('organizers')}
            className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition-all ${
              activeTab === 'organizers' 
                ? 'bg-accent-neon text-bg-base shadow-glow' 
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            <Award className="w-4 h-4" />
            Treinadores
          </button>
        </div>
        
        {/* Tab Contents */}
        <div className="mt-8 transition-all duration-300">
          
          {/* Tab 1: Athletes */}
          {activeTab === 'athletes' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center bg-bg-card/30 border border-border-subtle p-6 md:p-10 rounded-3xl animate-fade-in">
              <div className="lg:col-span-7 space-y-6">
                <h4 className="text-2xl font-bold">Potencialize sua rotina como tenista competitivo</h4>
                <p className="text-text-secondary text-sm md:text-base leading-relaxed">
                  Simplifique o planejamento da sua temporada. O Tenfy busca os melhores torneios para você, sinaliza sua categoria exata e cria uma agenda esportiva para você não perder tempo e focar em ganhar pontos no ranking.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="flex items-start gap-2.5">
                    <span className="p-1 rounded bg-accent-neon/10 text-accent-neon shrink-0 mt-0.5"><Check className="w-3.5 h-3.5" /></span>
                    <p className="text-xs text-text-secondary font-medium"><strong className="text-text-primary">Filtro técnico por classe:</strong> Veja torneios compatíveis com seu nível.</p>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="p-1 rounded bg-accent-neon/10 text-accent-neon shrink-0 mt-0.5"><Check className="w-3.5 h-3.5" /></span>
                    <p className="text-xs text-text-secondary font-medium"><strong className="text-text-primary">Seleção regional:</strong> Escolha os estados onde aceita viajar para jogar.</p>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="p-1 rounded bg-accent-neon/10 text-accent-neon shrink-0 mt-0.5"><Check className="w-3.5 h-3.5" /></span>
                    <p className="text-xs text-text-secondary font-medium"><strong className="text-text-primary">Inscrições com um clique:</strong> Links diretos e atualizados para federar-se e inscrever-se.</p>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="p-1 rounded bg-accent-neon/10 text-accent-neon shrink-0 mt-0.5"><Check className="w-3.5 h-3.5" /></span>
                    <p className="text-xs text-text-secondary font-medium"><strong className="text-text-primary">Lista de favoritos:</strong> Acompanhe chaves e resultados das competições salvas.</p>
                  </div>
                </div>
              </div>
              <div className="lg:col-span-5 flex justify-center">
                <div className="relative p-6 rounded-3xl border border-border-subtle bg-bg-card shadow-card max-w-sm w-full space-y-4">
                  <div className="flex items-center justify-between border-b border-border-subtle pb-3">
                    <span className="text-xs text-text-muted">PERFIL ATLETA</span>
                    <span className="badge bg-accent-neon/15 text-accent-neon border border-accent-neon/30">ATIVO</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-accent-blue/10 flex items-center justify-center text-accent-blue font-bold">TH</div>
                    <div>
                      <h5 className="text-sm font-bold">Thiago Monteiro (Simulado)</h5>
                      <p className="text-[10px] text-text-muted">1ª Classe • SP • 28 anos</p>
                    </div>
                  </div>
                  <div className="bg-bg-elevated p-3 rounded-xl border border-border-subtle space-y-2">
                    <div className="flex justify-between text-xs">
                      <span className="text-text-secondary">Torneios Compatíveis</span>
                      <span className="font-bold text-accent-neon">12 Torneios</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-text-secondary">Favoritos na Agenda</span>
                      <span className="font-bold text-accent-blue">4 Salvos</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
          
          {/* Tab 2: Parents */}
          {activeTab === 'parents' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center bg-bg-card/30 border border-border-subtle p-6 md:p-10 rounded-3xl animate-fade-in">
              <div className="lg:col-span-7 space-y-6">
                <h4 className="text-2xl font-bold">Gerenciamento completo e paz de espírito para os pais</h4>
                <p className="text-text-secondary text-sm md:text-base leading-relaxed">
                  Sabemos que a logística de torneios infanto-juvenis pode ser um pesadelo organizacional. O Tenfy facilita o gerenciamento de perfis de filhos atletas, unificando cronogramas, custos, localizações e prazos para você planejar viagens e nunca perder uma data importante.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="flex items-start gap-2.5">
                    <span className="p-1 rounded bg-accent-neon/10 text-accent-neon shrink-0 mt-0.5"><Check className="w-3.5 h-3.5" /></span>
                    <p className="text-xs text-text-secondary font-medium"><strong className="text-text-primary">Múltiplos atletas:</strong> Adicione e gerencie os perfis de todos os seus filhos na mesma conta.</p>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="p-1 rounded bg-accent-neon/10 text-accent-neon shrink-0 mt-0.5"><Check className="w-3.5 h-3.5" /></span>
                    <p className="text-xs text-text-secondary font-medium"><strong className="text-text-primary">Controle de prazos:</strong> Notificações push e e-mail antes do fechamento de inscrições.</p>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="p-1 rounded bg-accent-neon/10 text-accent-neon shrink-0 mt-0.5"><Check className="w-3.5 h-3.5" /></span>
                    <p className="text-xs text-text-secondary font-medium"><strong className="text-text-primary">Logística mapeada:</strong> Tenha rotas de clubes, hotéis parceiros e custos consolidados.</p>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="p-1 rounded bg-accent-neon/10 text-accent-neon shrink-0 mt-0.5"><Check className="w-3.5 h-3.5" /></span>
                    <p className="text-xs text-text-secondary font-medium"><strong className="text-text-primary">Histórico consolidado:</strong> Acompanhe a evolução do nível de jogo deles na plataforma.</p>
                  </div>
                </div>
              </div>
              <div className="lg:col-span-5 flex justify-center">
                <div className="relative p-6 rounded-3xl border border-border-subtle bg-bg-card shadow-card max-w-sm w-full space-y-4">
                  <div className="flex items-center justify-between border-b border-border-subtle pb-3">
                    <span className="text-xs text-text-muted">PAINEL DO RESPONSÁVEL</span>
                    <span className="badge bg-accent-orange/15 text-accent-orange border border-accent-orange/30">LOGÍSTICA</span>
                  </div>
                  <div className="space-y-3">
                    <h5 className="text-xs font-bold text-text-secondary">Filhos sob Gestão</h5>
                    
                    <div className="flex items-center justify-between bg-bg-elevated p-2 rounded-lg border border-border-subtle text-xs">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full bg-accent-neon/20 flex items-center justify-center text-accent-neon text-[10px] font-bold">L</div>
                        <span className="font-semibold">Lucas (12 Anos)</span>
                      </div>
                      <span className="text-[10px] text-accent-neon bg-accent-neon/10 px-1.5 py-0.5 rounded font-bold">12u Masc</span>
                    </div>

                    <div className="flex items-center justify-between bg-bg-elevated p-2 rounded-lg border border-border-subtle text-xs">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full bg-accent-blue/20 flex items-center justify-center text-accent-blue text-[10px] font-bold">M</div>
                        <span className="font-semibold">Maria (14 Anos)</span>
                      </div>
                      <span className="text-[10px] text-accent-blue bg-accent-blue/10 px-1.5 py-0.5 rounded font-bold">14u Fem</span>
                    </div>

                  </div>
                </div>
              </div>
            </div>
          )}
          
          {/* Tab 3: Organizers */}
          {activeTab === 'organizers' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center bg-bg-card/30 border border-border-subtle p-6 md:p-10 rounded-3xl animate-fade-in">
              <div className="lg:col-span-7 space-y-6">
                <h4 className="text-2xl font-bold">Maximize o desempenho e o engajamento dos seus alunos</h4>
                <p className="text-text-secondary text-sm md:text-base leading-relaxed">
                  Para técnicos, academias e organizadores, o Tenfy oferece uma visão macro das competições dos atletas sob sua orientação. Monitore quem está inscrito, organize chaves de treinamento, receba dados sobre a frequência de torneios jogados e potencialize os resultados do seu time.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="flex items-start gap-2.5">
                    <span className="p-1 rounded bg-accent-neon/10 text-accent-neon shrink-0 mt-0.5"><Check className="w-3.5 h-3.5" /></span>
                    <p className="text-xs text-text-secondary font-medium"><strong className="text-text-primary">Monitor de alunos:</strong> Acompanhe as agendas de todos os seus alunos cadastrados.</p>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="p-1 rounded bg-accent-neon/10 text-accent-neon shrink-0 mt-0.5"><Check className="w-3.5 h-3.5" /></span>
                    <p className="text-xs text-text-secondary font-medium"><strong className="text-text-primary">Recomendação técnica:</strong> Indique torneios diretamente para o perfil de um aluno.</p>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="p-1 rounded bg-accent-neon/10 text-accent-neon shrink-0 mt-0.5"><Check className="w-3.5 h-3.5" /></span>
                    <p className="text-xs text-text-secondary font-medium"><strong className="text-text-primary">Divulgação de ligas:</strong> Promova os torneios da sua academia com alcance focado.</p>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="p-1 rounded bg-accent-neon/10 text-accent-neon shrink-0 mt-0.5"><Check className="w-3.5 h-3.5" /></span>
                    <p className="text-xs text-text-secondary font-medium"><strong className="text-text-primary">Relatórios técnicos:</strong> Analise as taxas de vitória e consistência de jogo.</p>
                  </div>
                </div>
              </div>
              <div className="lg:col-span-5 flex justify-center">
                <div className="relative p-6 rounded-3xl border border-border-subtle bg-bg-card shadow-card max-w-sm w-full space-y-4">
                  <div className="flex items-center justify-between border-b border-border-subtle pb-3">
                    <span className="text-xs text-text-muted">PAINEL DO TREINADOR</span>
                    <span className="badge bg-accent-neon/15 text-accent-neon border border-accent-neon/30">SUPERVISÃO</span>
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-text-secondary font-medium">Alunos na Equipe</span>
                      <span className="font-bold text-text-primary">15 tenistas</span>
                    </div>
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-text-secondary font-medium">Inscritos esta semana</span>
                      <span className="font-bold text-accent-neon">5 ativos</span>
                    </div>
                    <div className="h-1.5 w-full bg-bg-elevated rounded-full overflow-hidden mt-1">
                      <div className="h-full bg-accent-neon w-1/3" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
          
        </div>
      </section>

      {/* ─── HOW IT WORKS (COMO FUNCIONA) ────────────────────────────────── */}
      <section id="como-funciona" className="py-20 bg-bg-card/40 border-y border-border-subtle px-4">
        <div className="max-w-6xl mx-auto space-y-12">
          
          <div className="text-center max-w-2xl mx-auto space-y-4">
            <h2 className="text-xs uppercase font-extrabold tracking-widest text-accent-neon">Fluxo do Usuário</h2>
            <h3 className="text-3xl md:text-4xl font-bold">Quatro passos para transformar sua temporada</h3>
            <p className="text-text-secondary text-sm md:text-base">
              Nunca foi tão rápido planejar seus treinos e garantir sua vaga nos melhores torneios locais e nacionais.
            </p>
          </div>
          
          {/* Steps Timeline Grid */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 relative">
            
            {/* Step 1 */}
            <div className="space-y-3 relative group">
              <div className="w-10 h-10 rounded-full bg-accent-neon text-bg-base font-extrabold flex items-center justify-center text-sm shadow-glow group-hover:scale-110 transition-transform duration-300">
                1
              </div>
              <h4 className="text-base font-bold pt-2">Crie seu Perfil</h4>
              <p className="text-xs text-text-secondary leading-relaxed">
                Configure sua classe técnica (1ª a 6ª classe, iniciante, etc.), sua idade esportiva, localização e estados onde deseja jogar.
              </p>
            </div>
            
            {/* Step 2 */}
            <div className="space-y-3 relative group">
              <div className="w-10 h-10 rounded-full bg-bg-elevated border border-border-subtle text-accent-neon font-extrabold flex items-center justify-center text-sm shadow-card group-hover:scale-110 transition-transform duration-300">
                2
              </div>
              <h4 className="text-base font-bold pt-2">Filtro Inteligente</h4>
              <p className="text-xs text-text-secondary leading-relaxed">
                Nosso algoritmo lê instantaneamente os regulamentos oficiais e lista somente os torneios onde você é elegível.
              </p>
            </div>
            
            {/* Step 3 */}
            <div className="space-y-3 relative group">
              <div className="w-10 h-10 rounded-full bg-bg-elevated border border-border-subtle text-accent-neon font-extrabold flex items-center justify-center text-sm shadow-card group-hover:scale-110 transition-transform duration-300">
                3
              </div>
              <h4 className="text-base font-bold pt-2">Planeje na Agenda</h4>
              <p className="text-xs text-text-secondary leading-relaxed">
                Salve torneios na sua Watchlist para receber notificações automáticas antes que as inscrições encerrem.
              </p>
            </div>
            
            {/* Step 4 */}
            <div className="space-y-3 relative group">
              <div className="w-10 h-10 rounded-full bg-bg-elevated border border-border-subtle text-accent-neon font-extrabold flex items-center justify-center text-sm shadow-card group-hover:scale-110 transition-transform duration-300">
                4
              </div>
              <h4 className="text-base font-bold pt-2">Inscrição Integrada</h4>
              <p className="text-xs text-text-secondary leading-relaxed">
                Use os links diretos para a página oficial do torneio no portal da federação correspondente, sem erros ou burocracia.
              </p>
            </div>
            
          </div>
          
        </div>
      </section>

      {/* ─── INTERACTIVE SIMULATOR (SIMULADOR DE TORNEIOS) ────────────────── */}
      <section id="simulador" className="py-20 px-4 max-w-6xl mx-auto space-y-12">
        
        <div className="text-center max-w-2xl mx-auto space-y-4">
          <h2 className="text-xs uppercase font-extrabold tracking-widest text-accent-blue">Experimente Agora</h2>
          <h3 className="text-3xl md:text-4xl font-bold">Simulador de Compatibilidade</h3>
          <p className="text-text-secondary text-sm md:text-base">
            Selecione seu estado e sua classe esportiva abaixo para experimentar nosso algoritmo de elegibilidade inteligente funcionando em tempo real.
          </p>
        </div>
        
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          
          {/* Left: Simulator Filters */}
          <div className="lg:col-span-4 bg-bg-card border border-border-subtle rounded-3xl p-6 space-y-6 shadow-card sticky top-20">
            <h4 className="text-base font-bold flex items-center gap-2 border-b border-border-subtle pb-3">
              <Filter className="w-4 h-4 text-accent-neon" />
              Configurar Perfil
            </h4>
            
            {/* State Filter */}
            <div className="space-y-2">
              <label className="text-xs text-text-secondary font-medium">Estado de Preferência</label>
              <div className="flex flex-wrap gap-2">
                {['Todos', 'SP', 'RJ', 'MG', 'PR', 'RS'].map((st) => (
                  <button
                    key={st}
                    onClick={() => setSelectedState(st)}
                    className={`py-1.5 px-3 rounded-lg text-xs font-semibold border transition-all ${
                      selectedState === st 
                        ? 'bg-accent-neon/15 text-accent-neon border-accent-neon' 
                        : 'bg-bg-elevated/40 text-text-secondary border-border-subtle hover:bg-bg-elevated'
                    }`}
                  >
                    {st === 'Todos' ? 'Todos Estados' : st}
                  </button>
                ))}
              </div>
            </div>
            
            {/* Tennis Class Filter */}
            <div className="space-y-2">
              <label className="text-xs text-text-secondary font-medium">Sua Classe Esportiva</label>
              <div className="flex flex-wrap gap-2">
                {['Todas', '1ª Classe', '2ª Classe', '3ª Classe', '4ª Classe', 'Iniciante'].map((cl) => (
                  <button
                    key={cl}
                    onClick={() => setSelectedClass(cl)}
                    className={`py-1.5 px-3 rounded-lg text-xs font-semibold border transition-all ${
                      selectedClass === cl 
                        ? 'bg-accent-neon/15 text-accent-neon border-accent-neon' 
                        : 'bg-bg-elevated/40 text-text-secondary border-border-subtle hover:bg-bg-elevated'
                    }`}
                  >
                    {cl}
                  </button>
                ))}
              </div>
            </div>
            
            {/* Help box */}
            <div className="bg-bg-elevated/50 p-4 rounded-2xl border border-border-subtle/50 text-[11px] text-text-muted leading-relaxed">
              💡 <strong>Como Funciona:</strong> No aplicativo completo, o Tenfy cruza esses dados com os regulamentos de federações como FPT e CBT de forma totalmente automatizada.
            </div>
          </div>
          
          {/* Right: Simulated Tournament Cards */}
          <div className="lg:col-span-8 space-y-4">
            <div className="flex justify-between items-center text-xs text-text-secondary font-semibold px-2 mb-1">
              <span>Resultados Filtrados ({filteredTournaments.length})</span>
              <span>Visualização em tempo real</span>
            </div>
            
            {filteredTournaments.length === 0 ? (
              <div className="card text-center py-12 text-text-muted text-sm border-dashed">
                Nenhum torneio encontrado para o perfil selecionado. Tente alterar os filtros.
              </div>
            ) : (
              <div className="space-y-4">
                {filteredTournaments.map((t) => {
                  // Calculate eligibility
                  const isEligible = selectedClass === 'Todas' || t.classes.includes(selectedClass);
                  
                  return (
                    <div 
                      key={t.id} 
                      className={`card border-l-4 transition-all duration-300 hover:scale-[1.01] ${
                        isEligible 
                          ? 'border-l-accent-neon hover:border-accent-neon/60 bg-bg-card' 
                          : 'border-l-accent-orange/60 bg-bg-card opacity-80'
                      }`}
                    >
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="space-y-2">
                          
                          {/* Badges */}
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] uppercase font-extrabold tracking-widest text-accent-neon bg-accent-neon/10 px-2 py-0.5 rounded">
                              {t.federation}
                            </span>
                            <span className="badge bg-bg-elevated border border-border-subtle text-[10px]">
                              {t.state}
                            </span>
                            
                            {/* Eligibility Badge */}
                            {isEligible ? (
                              <span className="text-[10px] font-bold text-accent-neon bg-accent-neon/10 border border-accent-neon/30 px-2 py-0.5 rounded flex items-center gap-1">
                                <span className="w-1.5 h-1.5 rounded-full bg-accent-neon animate-pulse" />
                                100% Elegível
                              </span>
                            ) : (
                              <span className="text-[10px] font-bold text-accent-orange bg-accent-orange/10 border border-accent-orange/30 px-2 py-0.5 rounded flex items-center gap-1">
                                Incompatível (Classe)
                              </span>
                            )}
                          </div>
                          
                          {/* Title */}
                          <h5 className="font-bold text-sm md:text-base group-hover:text-accent-neon transition-colors">
                            {t.title}
                          </h5>
                          
                          {/* Info Rows */}
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-text-muted">
                            <div className="flex items-center gap-1">
                              <MapPin className="w-3.5 h-3.5 shrink-0" />
                              <span className="truncate">{t.location}</span>
                            </div>
                            <div className="flex items-center gap-1">
                              <Calendar className="w-3.5 h-3.5 shrink-0" />
                              <span>{t.startDate} - {t.endDate}</span>
                            </div>
                          </div>
                          
                        </div>
                        
                        {/* Right: CTA & Deadline */}
                        <div className="flex sm:flex-col items-center sm:items-end justify-between sm:justify-center border-t sm:border-t-0 border-border-subtle/50 pt-3 sm:pt-0 gap-3">
                          <div className="text-right sm:space-y-1">
                            <p className="text-[10px] text-text-muted">Inscrições até</p>
                            <p className="text-xs font-bold text-accent-orange flex items-center gap-1 justify-end">
                              <Clock className="w-3 h-3" />
                              {t.closingDate}
                            </p>
                          </div>
                          <Link 
                            to={isAuthenticated ? "/inicio" : "/register"} 
                            className="btn-primary !py-1.5 !px-3.5 text-xs font-bold shrink-0 shadow-none hover:shadow-glow"
                          >
                            Inscrever-se
                          </Link>
                        </div>
                        
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
          
        </div>
      </section>

      {/* ─── VISUAL GALLERY (SEÇÃO VISUAL COM IMAGENS) ──────────────────── */}
      <section id="galeria" className="py-20 bg-bg-card/40 border-y border-border-subtle px-4">
        <div className="max-w-6xl mx-auto space-y-12">
          
          <div className="text-center max-w-2xl mx-auto space-y-4">
            <h2 className="text-xs uppercase font-extrabold tracking-widest text-accent-neon">Identidade Visual & Marca</h2>
            <h3 className="text-3xl md:text-4xl font-bold">Universo Visual Tenfy</h3>
            <p className="text-text-secondary text-sm md:text-base">
              Nossa marca reflete tecnologia, energia do esporte e precisão. Conheça as aplicações reais de nossa identidade visual presentes no projeto.
            </p>
          </div>
          
          {/* Gallery Masonry */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            
            {/* Visual Item 1 */}
            <div className="group relative overflow-hidden rounded-3xl border border-border-subtle bg-bg-card/50 p-4 shadow-card hover:-translate-y-1 transition-all duration-300">
              <div className="aspect-[4/3] rounded-2xl overflow-hidden bg-bg-elevated relative flex items-center justify-center">
                <img 
                  src="/img_lp/Manual da marca - Aplicações.png" 
                  alt="Aplicações Mobile e Web" 
                  className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" 
                  loading="lazy"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-bg-base/90 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-end p-4">
                  <span className="text-xs font-bold text-accent-neon">Aplicações Reais Mobile & Web</span>
                </div>
              </div>
              <h5 className="font-bold text-sm mt-4">Manual da Marca — Aplicações</h5>
              <p className="text-xs text-text-muted mt-1">Mockups representativos da interface web e mobile adaptável.</p>
            </div>
            
            {/* Visual Item 2 */}
            <div className="group relative overflow-hidden rounded-3xl border border-border-subtle bg-bg-card/50 p-4 shadow-card hover:-translate-y-1 transition-all duration-300">
              <div className="aspect-[4/3] rounded-2xl overflow-hidden bg-bg-elevated relative flex items-center justify-center">
                <img 
                  src="/img_lp/Manual da marca - Sistema Visual.png" 
                  alt="Sistema Visual" 
                  className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" 
                  loading="lazy"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-bg-base/90 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-end p-4">
                  <span className="text-xs font-bold text-accent-neon">Design System & Tipografia</span>
                </div>
              </div>
              <h5 className="font-bold text-sm mt-4">Sistema Visual de Cores</h5>
              <p className="text-xs text-text-muted mt-1">Paleta com tom vibrante Lima Tênis (#C6EF21) e Azul Profundo (#0A1330).</p>
            </div>
            
            {/* Visual Item 3 */}
            <div className="group relative overflow-hidden rounded-3xl border border-border-subtle bg-bg-card/50 p-4 shadow-card hover:-translate-y-1 transition-all duration-300">
              <div className="aspect-[4/3] rounded-2xl overflow-hidden bg-bg-elevated relative flex items-center justify-center">
                <img 
                  src="/img_lp/Ícones e variações.png" 
                  alt="Ícones da Marca" 
                  className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" 
                  loading="lazy"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-bg-base/90 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-end p-4">
                  <span className="text-xs font-bold text-accent-neon">Ícones e Detalhes da Marca</span>
                </div>
              </div>
              <h5 className="font-bold text-sm mt-4">Ícones & Variações de Logo</h5>
              <p className="text-xs text-text-muted mt-1">Símbolos e marcas geométricas pensadas para melhor legibilidade digital.</p>
            </div>
            
          </div>
          
        </div>
      </section>

      {/* ─── CALL TO ACTION FINAL (CTA) ──────────────────────────────────── */}
      <section className="py-20 px-4 max-w-5xl mx-auto">
        <div className="relative rounded-3xl border border-accent-neon/30 bg-bg-card p-8 md:p-16 text-center space-y-6 shadow-glow overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-tr from-accent-neon/5 to-accent-blue/5 pointer-events-none" />
          
          <h3 className="text-3xl md:text-5xl font-extrabold max-w-2xl mx-auto leading-tight">
            Pronto para revolucionar seu calendário esportivo?
          </h3>
          <p className="text-text-secondary text-sm md:text-base max-w-xl mx-auto leading-relaxed">
            Junte-se a centenas de tenistas que já não perdem nenhuma inscrição e competem sempre em categorias perfeitamente elegíveis.
          </p>
          
          <div className="pt-4 flex flex-col sm:flex-row items-center justify-center gap-4">
            {isAuthenticated ? (
              <Link to="/inicio" className="btn-primary flex items-center gap-2 hover:scale-105 transition-transform duration-300">
                Acessar Plataforma <ArrowRight className="w-4 h-4" />
              </Link>
            ) : (
              <>
                <Link to="/register" className="btn-primary hover:scale-105 transition-transform duration-300">
                  Criar Conta Grátis
                </Link>
                <Link to="/login" className="btn-secondary hover:scale-105 transition-transform duration-300">
                  Entrar no Perfil
                </Link>
              </>
            )}
          </div>
        </div>
      </section>

      {/* ─── FOOTER ──────────────────────────────────────────────────────── */}
      <footer className="border-t border-border-subtle bg-bg-card py-12 px-4 transition-colors duration-300">
        <div className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-8">
          
          {/* Column 1: Brand details */}
          <div className="space-y-4 col-span-1 md:col-span-2">
            <Link to="/" className="inline-block">
              <img src="/logos/logo_clara.png" alt="Tenfy" className="h-10 w-auto object-contain dark:hidden" />
              <img src="/logos/logo_escura.png" alt="Tenfy" className="h-10 w-auto object-contain hidden dark:block" />
            </Link>
            <p className="text-xs text-text-secondary max-w-sm leading-relaxed">
              O Tenfy é o agregador inteligente de torneios oficiais de tênis no Brasil. Criamos tecnologia para conectar atletas, pais e organizadores no ecossistema esportivo.
            </p>
            <p className="text-[10px] text-text-muted">
              © {new Date().getFullYear()} Tenfy. Todos os direitos reservados.
            </p>
          </div>
          
          {/* Column 2: Platform Links */}
          <div className="space-y-3">
            <h5 className="text-xs uppercase font-extrabold tracking-widest text-text-primary">Navegação</h5>
            <ul className="space-y-2 text-xs text-text-secondary font-medium">
              <li><a href="#recursos" className="hover:text-accent-neon transition-colors">Recursos</a></li>
              <li><a href="#beneficios" className="hover:text-accent-neon transition-colors">Benefícios</a></li>
              <li><a href="#como-funciona" className="hover:text-accent-neon transition-colors">Como Funciona</a></li>
              <li><a href="#simulador" className="hover:text-accent-neon transition-colors">Testar Simulador</a></li>
            </ul>
          </div>
          
          {/* Column 3: Legal & Support */}
          <div className="space-y-3">
            <h5 className="text-xs uppercase font-extrabold tracking-widest text-text-primary">Legal & Suporte</h5>
            <ul className="space-y-2 text-xs text-text-secondary font-medium">
              <li>
                <Link to="/politica-privacidade" className="hover:text-accent-neon transition-colors">
                  Política de Privacidade
                </Link>
              </li>
              <li>
                <Link to="/login" className="hover:text-accent-neon transition-colors">
                  Acesso Restrito
                </Link>
              </li>
              <li>
                <span className="text-text-muted cursor-not-allowed">Suporte: contato@tenfy.com.br</span>
              </li>
            </ul>
          </div>
          
        </div>
      </footer>
      
    </div>
  );
};
