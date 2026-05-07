"""Celery tasks for the accounts app — email dispatch with retry and HTML templates."""
import logging
from html import escape as _esc

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger('apps.accounts')

APP_NAME   = 'Tenfy'
APP_SLOGAN = 'Plataforma de Tênis'
BRAND      = '#C6EF21'
BRAND_DARK = '#a8cc10'
BG         = '#0A1330'
CARD       = '#1D232D'
BORDER     = '#2a3040'
TEXT       = '#F6F7FA'
MUTED      = '#9CA3AF'
SUBTLE     = '#4B5563'
DANGER     = '#ef4444'

def _frontend() -> str:
    """Always read from settings so domain changes don't require a code deploy."""
    return getattr(settings, 'FRONTEND_URL', 'https://tennis.app.br').rstrip('/')


def _html(title: str, content: str, preview: str = '') -> str:
    """Render a complete branded email. preview = hidden preheader text.
    All user-controlled values must be escaped with _esc() before passing as content."""
    frontend = _frontend()
    return f"""<!DOCTYPE html>
<html lang="pt-BR" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <meta http-equiv="X-UA-Compatible" content="IE=edge"/>
  <title>{title}</title>
  <!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:{BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;color:{TEXT};-webkit-font-smoothing:antialiased}}
    .wrapper{{max-width:580px;margin:0 auto;padding:40px 16px 60px}}
    .header{{text-align:center;padding-bottom:32px}}
    .logo{{display:inline-block;background:{CARD};border:1px solid {BORDER};border-radius:16px;padding:12px 24px}}
    .logo-icon{{font-size:28px;display:block;line-height:1}}
    .logo-name{{font-size:18px;font-weight:800;color:{BRAND};letter-spacing:-0.5px;margin-top:4px}}
    .card{{background:{CARD};border:1px solid {BORDER};border-radius:20px;padding:36px 32px;margin-bottom:24px}}
    h1{{font-size:22px;font-weight:700;color:{TEXT};margin-bottom:8px;line-height:1.3}}
    .subtitle{{font-size:15px;color:{MUTED};line-height:1.6;margin-bottom:24px}}
    p{{font-size:14px;color:{MUTED};line-height:1.7;margin:12px 0}}
    .divider{{border:none;border-top:1px solid {BORDER};margin:24px 0}}
    /* OTP Code block */
    .otp-wrap{{background:{BG};border:1px solid {BRAND}33;border-radius:14px;padding:28px 20px;text-align:center;margin:24px 0}}
    .otp-code{{font-size:48px;font-weight:900;color:{BRAND};letter-spacing:14px;font-family:'Courier New',monospace;line-height:1}}
    .otp-timer{{margin-top:10px;font-size:12px;color:{MUTED}}}
    .otp-timer strong{{color:{TEXT}}}
    /* Button */
    .btn-wrap{{text-align:center;margin:28px 0}}
    .btn{{display:inline-block;background:{BRAND};color:{BG};font-weight:700;font-size:15px;padding:14px 36px;border-radius:12px;text-decoration:none;letter-spacing:0.2px}}
    .btn:hover{{background:{BRAND_DARK}}}
    /* Link fallback */
    .link-fallback{{background:{BG};border:1px solid {BORDER};border-radius:10px;padding:14px 16px;margin-top:16px;word-break:break-all}}
    .link-fallback p{{font-size:12px;color:{SUBTLE};margin:0 0 6px}}
    .link-fallback a{{font-size:12px;color:{MUTED};text-decoration:underline;word-break:break-all}}
    /* Alert / warning box */
    .alert{{background:#ef444410;border:1px solid #ef444430;border-radius:10px;padding:12px 14px;margin-top:20px}}
    .alert p{{font-size:13px;color:#ef4444;margin:0}}
    /* Info box */
    .info{{background:{BRAND}08;border:1px solid {BRAND}20;border-radius:10px;padding:14px 16px;margin-top:16px}}
    .info p{{font-size:13px;color:{MUTED};margin:0;line-height:1.6}}
    .info strong{{color:{TEXT}}}
    /* Footer */
    .footer{{text-align:center;padding-top:8px}}
    .footer p{{font-size:12px;color:{SUBTLE};line-height:1.7;margin:4px 0}}
    .footer a{{color:{SUBTLE};text-decoration:underline}}
    .footer-logo{{font-size:13px;font-weight:700;color:{MUTED};margin-bottom:8px}}
    /* Mobile */
    @media(max-width:600px){{
      .card{{padding:24px 18px}}
      .otp-code{{font-size:38px;letter-spacing:10px}}
      h1{{font-size:19px}}
    }}
  </style>
</head>
<body>
  {'<span style="display:none;max-height:0;overflow:hidden;mso-hide:all;">'+preview+'</span>' if preview else ''}
  <div class="wrapper">

    <!-- Logo -->
    <div class="header">
      <div class="logo">
        <span class="logo-name" style="font-size:24px;font-weight:900;letter-spacing:-1px;">{APP_NAME}</span>
      </div>
    </div>

    <!-- Card -->
    <div class="card">
      {content}
    </div>

    <!-- Footer -->
    <div class="footer">
      <p class="footer-logo">{APP_NAME}</p>
      <p>{APP_SLOGAN}</p>
      <p><a href="{frontend}">{frontend}</a></p>
      <hr style="border:none;border-top:1px solid {BORDER};margin:16px 0"/>
      <p>Você recebe este e-mail porque possui uma conta no {APP_NAME}.</p>
      <p>Se não reconhece esta ação, ignore este e-mail — sua conta continua segura.</p>
    </div>

  </div>
</body>
</html>"""


def _send(subject: str, to: str, text: str, html: str):
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', f'no-reply@tennis.app.br')
    msg = EmailMultiAlternatives(subject=subject, body=text, from_email=from_email, to=[to])
    msg.attach_alternative(html, 'text/html')
    msg.send(fail_silently=False)


# ── OTP Email ──────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=60, acks_late=True)
def send_otp_email(self, user_id: int, email: str, full_name: str, code: str, subject_key: str = 'verify'):
    # _esc() prevents XSS if full_name contains HTML characters
    name = _esc((full_name or email.split('@')[0]).split(' ')[0].capitalize())

    cfg = {
        'verify': {
            'subject': f'[{APP_NAME}] Verifique seu e-mail',
            'preview': f'Seu código de verificação é {code} — válido por 10 minutos.',
            'title': 'Verifique seu e-mail ✉️',
            'subtitle': f'Olá, <strong style="color:{TEXT}">{name}</strong>! Para ativar sua conta no {APP_NAME}, insira o código abaixo no aplicativo.',
        },
        'resend': {
            'subject': f'[{APP_NAME}] Novo código de verificação',
            'preview': f'Código atualizado: {code} — válido por 10 minutos.',
            'title': 'Novo código de verificação 🔄',
            'subtitle': f'Olá, <strong style="color:{TEXT}">{name}</strong>! Você solicitou um novo código. Use-o abaixo para verificar seu e-mail.',
        },
        'reset': {
            'subject': f'[{APP_NAME}] Código para redefinir senha',
            'preview': f'Use o código {code} para redefinir sua senha.',
            'title': 'Redefinição de senha 🔐',
            'subtitle': f'Olá, <strong style="color:{TEXT}">{name}</strong>! Use o código abaixo para redefinir sua senha.',
        },
    }
    c = cfg.get(subject_key, cfg['verify'])

    content = f"""
      <h1>{c['title']}</h1>
      <p class="subtitle">{c['subtitle']}</p>

      <div class="otp-wrap">
        <div class="otp-code">{code}</div>
        <div class="otp-timer">Válido por <strong>10 minutos</strong> · Não compartilhe com ninguém</div>
      </div>

      <div class="info">
        <p>💡 Abra o <strong>{APP_NAME}</strong> e insira este código na tela de verificação.</p>
      </div>

      <hr class="divider"/>
      <p style="font-size:13px;color:{SUBTLE}">Se você não solicitou este código, ignore este e-mail. Nenhuma ação é necessária.</p>
    """

    html_body = _html(c['subject'], content, c['preview'])
    text_body = (
        f'Olá {name},\n\n'
        f'Seu código de verificação é: {code}\n\n'
        f'Válido por 10 minutos. Não compartilhe com ninguém.\n\n'
        f'Se não foi você, ignore este e-mail.\n\n'
        f'— {APP_NAME} | {_frontend()}'
    )

    try:
        _send(c['subject'], email, text_body, html_body)
        logger.info('OTP email dispatched to user %s', user_id)
    except Exception as exc:
        logger.warning('OTP email failed for user %s (attempt %d): %s', user_id, self.request.retries + 1, exc)
        raise self.retry(exc=exc)


# ── Password Reset Email ───────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=60, acks_late=True)
def send_password_reset_email(self, user_id: int, email: str, full_name: str, reset_url: str):
    """Password reset email. reset_url contains uid+token — NEVER logged."""
    name = _esc((full_name or email.split('@')[0]).split(' ')[0].capitalize())
    subject = f'[{APP_NAME}] Redefinição de senha'

    content = f"""
      <h1>Redefinir senha 🔐</h1>
      <p class="subtitle">
        Olá, <strong style="color:{TEXT}">{name}</strong>!
        Recebemos uma solicitação para redefinir a senha da sua conta no {APP_NAME}.
      </p>

      <div class="btn-wrap">
        <a href="{reset_url}" class="btn">Redefinir minha senha</a>
      </div>

      <div class="info">
        <p>⏱️ Este link é válido por <strong>24 horas</strong> e só pode ser usado uma vez.</p>
      </div>

      <div class="link-fallback">
        <p>Se o botão não funcionar, copie e cole este link no seu navegador:</p>
        <a href="{reset_url}">{reset_url}</a>
      </div>

      <hr class="divider"/>

      <div class="alert">
        <p>🔒 Se você não solicitou a redefinição de senha, ignore este e-mail. Sua senha atual não será alterada.</p>
      </div>
    """

    html_body = _html(subject, content, f'Redefina sua senha no {APP_NAME} — link válido por 24 horas.')
    text_body = (
        f'Olá {name},\n\n'
        f'Recebemos uma solicitação para redefinir a senha da sua conta no {APP_NAME}.\n\n'
        f'Acesse o link abaixo para criar uma nova senha (válido por 24h):\n\n'
        f'{reset_url}\n\n'
        f'Se não foi você, ignore este e-mail. Sua senha não será alterada.\n\n'
        f'— {APP_NAME} | {_frontend()}'
    )

    try:
        _send(subject, email, text_body, html_body)
        logger.info('Password reset email dispatched for user %s', user_id)
    except Exception as exc:
        logger.warning('Password reset email failed for user %s (attempt %d): %s', user_id, self.request.retries + 1, exc)
        raise self.retry(exc=exc)
