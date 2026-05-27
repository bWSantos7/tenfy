import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

export const PrivacyPolicyPage: React.FC = () => {
  const { theme } = useTheme();
  return (
    <div className="min-h-screen bg-bg-base text-text-primary">
      <div className="max-w-3xl mx-auto px-4 py-10">
        <div className="mb-8 flex items-center gap-4">
          <Link
            to="/login"
            className="text-text-secondary hover:text-accent-neon transition-colors flex items-center gap-1 text-sm"
          >
            <ArrowLeft size={16} />
            Voltar
          </Link>
        </div>

        <div className="flex items-center gap-4 mb-8">
          <img src={theme === 'dark' ? '/icons/logo_noturno_tr.png' : '/icons/logo_diurna_tr.png'} alt="Tenfy" className="w-12 h-12 object-contain" />
          <div>
            <h1 className="text-2xl font-bold">Política de Privacidade</h1>
            <p className="text-text-secondary text-sm mt-1">Última atualização: maio de 2026</p>
          </div>
        </div>

        <div className="space-y-8 text-text-secondary leading-relaxed">

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">1. Sobre o Tenfy</h2>
            <p>
              O Tenfy é uma plataforma digital para jogadores de tênis, com foco em centralização de calendários de
              torneios, análise de elegibilidade por perfil e categoria, e gerenciamento de assinaturas. Esta Política
              de Privacidade descreve como coletamos, usamos, armazenamos e protegemos seus dados pessoais, em
              conformidade com a Lei Geral de Proteção de Dados (LGPD — Lei nº 13.709/2018).
            </p>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">2. Dados que coletamos</h2>
            <p className="mb-3">Coletamos apenas os dados necessários para o funcionamento da plataforma:</p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><strong className="text-text-primary">Dados de cadastro:</strong> nome, e-mail e senha (armazenada de forma criptografada).</li>
              <li><strong className="text-text-primary">Perfil esportivo:</strong> data de nascimento, gênero, nível de jogo, localização, preferências de modalidade e categorias de interesse.</li>
              <li><strong className="text-text-primary">Foto de perfil:</strong> imagem enviada voluntariamente pelo usuário.</li>
              <li><strong className="text-text-primary">Dados de assinatura:</strong> plano contratado, histórico de pagamentos e status da assinatura (processados via Asaas).</li>
              <li><strong className="text-text-primary">Dados de uso:</strong> torneios adicionados à watchlist, alertas configurados e preferências de notificação.</li>
              <li><strong className="text-text-primary">Dados técnicos:</strong> logs de acesso, endereço IP e informações do dispositivo para fins de segurança e monitoramento.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">3. Como usamos seus dados</h2>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li>Criar e gerenciar sua conta na plataforma.</li>
              <li>Exibir torneios e análises de compatibilidade com base no seu perfil esportivo.</li>
              <li>Processar assinaturas e pagamentos.</li>
              <li>Enviar notificações e alertas sobre torneios de seu interesse.</li>
              <li>Enviar e-mails transacionais (verificação de conta, recuperação de senha).</li>
              <li>Monitorar a segurança e integridade da plataforma.</li>
              <li>Cumprir obrigações legais e regulatórias.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">4. Base legal para o tratamento</h2>
            <p className="mb-3">Tratamos seus dados com base nas seguintes hipóteses legais previstas na LGPD:</p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><strong className="text-text-primary">Execução de contrato:</strong> dados necessários para fornecer os serviços contratados.</li>
              <li><strong className="text-text-primary">Consentimento:</strong> para funcionalidades opcionais como foto de perfil e notificações.</li>
              <li><strong className="text-text-primary">Legítimo interesse:</strong> segurança, prevenção a fraudes e melhoria da plataforma.</li>
              <li><strong className="text-text-primary">Obrigação legal:</strong> cumprimento de exigências legais e fiscais.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">5. Compartilhamento de dados</h2>
            <p className="mb-3">
              Não vendemos nem compartilhamos seus dados pessoais com terceiros para fins comerciais. Compartilhamos
              apenas com prestadores de serviços essenciais para o funcionamento da plataforma:
            </p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li><strong className="text-text-primary">Asaas:</strong> processamento de pagamentos e assinaturas.</li>
              <li><strong className="text-text-primary">Cloudinary:</strong> armazenamento seguro de imagens.</li>
              <li><strong className="text-text-primary">Resend:</strong> envio de e-mails transacionais.</li>
              <li><strong className="text-text-primary">Sentry:</strong> monitoramento de erros (dados anonimizados).</li>
              <li><strong className="text-text-primary">Railway:</strong> infraestrutura de hospedagem.</li>
            </ul>
            <p className="mt-3">
              Todos os prestadores são contratualmente obrigados a tratar seus dados com segurança e sigilo, conforme a LGPD.
            </p>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">6. Armazenamento e segurança</h2>
            <p>
              Seus dados são armazenados em servidores seguros com criptografia em trânsito (HTTPS/TLS) e em
              repouso. Senhas são armazenadas com hash criptográfico robusto. Implementamos controles de acesso,
              autenticação e monitoramento contínuo para proteger suas informações contra acesso não autorizado,
              perda ou vazamento.
            </p>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">7. Retenção dos dados</h2>
            <p>
              Mantemos seus dados pelo tempo necessário para prestação dos serviços e cumprimento de obrigações
              legais. Após o encerramento da conta, dados pessoais são anonimizados ou excluídos em até 90 dias,
              salvo obrigação legal de retenção por prazo maior.
            </p>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">8. Seus direitos (LGPD)</h2>
            <p className="mb-3">Nos termos da LGPD, você tem direito a:</p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li>Confirmar a existência de tratamento dos seus dados.</li>
              <li>Acessar os dados que temos sobre você.</li>
              <li>Corrigir dados incompletos, inexatos ou desatualizados.</li>
              <li>Solicitar a anonimização, bloqueio ou eliminação de dados desnecessários.</li>
              <li>Revogar o consentimento para tratamentos baseados em consentimento.</li>
              <li>Solicitar a portabilidade dos seus dados.</li>
              <li>Ser informado sobre o compartilhamento dos seus dados.</li>
              <li>Solicitar a eliminação dos dados tratados com base em consentimento.</li>
            </ul>
            <p className="mt-3">
              Para exercer qualquer desses direitos, entre em contato conosco pelo e-mail:{' '}
              <a href="mailto:privacidade@tennis.app.br" className="text-accent-neon hover:underline">
                privacidade@tennis.app.br
              </a>
            </p>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">9. Cookies e tecnologias similares</h2>
            <p>
              Utilizamos tokens de autenticação armazenados de forma segura no dispositivo para manter sua sessão
              ativa. Não utilizamos cookies de rastreamento para fins publicitários.
            </p>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">10. Menores de idade</h2>
            <p>
              O Tenfy é destinado a usuários com 18 anos ou mais, exceto no contexto do Plano Família, onde
              dependentes menores podem ter perfis gerenciados pelo responsável pagante. O cadastro de menores
              requer consentimento explícito do responsável legal, conforme exigido pela LGPD.
            </p>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">11. Alterações nesta política</h2>
            <p>
              Podemos atualizar esta Política de Privacidade periodicamente. Alterações relevantes serão comunicadas
              por e-mail ou notificação na plataforma. O uso continuado da plataforma após a notificação implica
              aceitação da versão atualizada.
            </p>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">12. Contato e Encarregado (DPO)</h2>
            <p className="mb-2">
              Para dúvidas, solicitações ou exercício dos seus direitos relacionados à privacidade:
            </p>
            <ul className="space-y-1 ml-2">
              <li>
                <strong className="text-text-primary">E-mail:</strong>{' '}
                <a href="mailto:privacidade@tennis.app.br" className="text-accent-neon hover:underline">
                  privacidade@tennis.app.br
                </a>
              </li>
              <li>
                <strong className="text-text-primary">Site:</strong>{' '}
                <a href="https://www.tennis.app.br" className="text-accent-neon hover:underline" target="_blank" rel="noopener noreferrer">
                  www.tennis.app.br
                </a>
              </li>
            </ul>
            <p className="mt-3">
              Referência legal:{' '}
              <a
                href="https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"
                className="text-accent-neon hover:underline"
                target="_blank"
                rel="noopener noreferrer"
              >
                Lei nº 13.709/2018 — LGPD
              </a>
            </p>
          </section>

        </div>

        <div className="mt-12 pt-8 border-t border-border-default text-center text-text-secondary text-sm">
          <p>© {new Date().getFullYear()} Tenfy. Todos os direitos reservados.</p>
        </div>
      </div>
    </div>
  );
};
