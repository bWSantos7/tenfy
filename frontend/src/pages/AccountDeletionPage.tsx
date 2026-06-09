import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

// Página pública (sem login) exigida pelas lojas de aplicativos: explica como o
// usuário exclui a própria conta e quais dados são removidos/retidos.
// Rota: /exclusao-de-conta (com alias /excluir-conta). Não pode exigir autenticação.
export const AccountDeletionPage: React.FC = () => {
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
          <img src="/logos/logo_aba.png" alt="Tenfy" className="w-12 h-12 object-contain" />
          <div>
            <h1 className="text-2xl font-bold">Exclusão de conta e dados</h1>
            <p className="text-text-secondary text-sm mt-1">Tenfy — como excluir sua conta</p>
          </div>
        </div>

        <div className="space-y-8 text-text-secondary leading-relaxed">

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">Como excluir sua conta pelo aplicativo</h2>
            <p className="mb-3">
              Você pode excluir sua conta do Tenfy a qualquer momento, diretamente no aplicativo ou no site,
              seguindo estes passos:
            </p>
            <ol className="list-decimal list-inside space-y-2 ml-2">
              <li>Faça login na sua conta.</li>
              <li>Abra o menu <strong className="text-text-primary">Configurações</strong>.</li>
              <li>Role até a seção <strong className="text-text-primary">Conta</strong>.</li>
              <li>Toque em <strong className="text-text-primary">Excluir minha conta</strong> e confirme.</li>
            </ol>
            <p className="mt-3">A exclusão é processada imediatamente após a confirmação.</p>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">Como solicitar a exclusão sem acesso ao app</h2>
            <p>
              Se você não conseguir acessar sua conta, envie um pedido de exclusão para{' '}
              <a href="mailto:privacidade@tenfy.com.br" className="text-accent-neon hover:underline">
                privacidade@tenfy.com.br
              </a>{' '}
              a partir do e-mail cadastrado, com o assunto <strong className="text-text-primary">"Excluir minha conta"</strong>.
              Concluímos a solicitação em até 30 dias após a confirmação de titularidade.
            </p>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">Quais dados são excluídos</h2>
            <p className="mb-3">Ao excluir a conta, removemos ou anonimizamos os seus dados pessoais, incluindo:</p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li>Dados de cadastro: nome, e-mail, telefone e foto de perfil.</li>
              <li>Perfil esportivo: data de nascimento, gênero, nível, localização, categorias e preferências.</li>
              <li>Watchlist, alertas e preferências de notificação.</li>
              <li>Credenciais de acesso (a senha é invalidada e a conta é desativada).</li>
            </ul>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">Quais dados podem ser retidos</h2>
            <p>
              Registros financeiros (pagamentos e assinaturas) e logs de auditoria podem ser mantidos de forma
              <strong className="text-text-primary"> anonimizada</strong> pelo período exigido por obrigações legais
              e fiscais, sem identificar você. Esses registros não são utilizados para nenhuma outra finalidade.
            </p>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">Prazo</h2>
            <p>
              A exclusão pelo aplicativo é imediata. Dados eventualmente retidos por obrigação legal são
              anonimizados ou eliminados conforme descrito na nossa{' '}
              <Link to="/politica-privacidade" className="text-accent-neon hover:underline">
                Política de Privacidade
              </Link>.
            </p>
          </section>

          <section>
            <h2 className="text-text-primary font-semibold text-lg mb-3">Contato</h2>
            <p>
              Dúvidas sobre exclusão de conta ou tratamento de dados:{' '}
              <a href="mailto:privacidade@tenfy.com.br" className="text-accent-neon hover:underline">
                privacidade@tenfy.com.br
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
