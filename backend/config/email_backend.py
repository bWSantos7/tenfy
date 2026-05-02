import logging
import sys

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):
    def __init__(self, api_key=None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or getattr(settings, 'RESEND_API_KEY', '')

    def open(self):
        return True

    def close(self):
        pass

    def send_messages(self, email_messages):
        import resend

        resend.api_key = self.api_key
        if not resend.api_key:
            print('[EMAIL] ERROR: RESEND_API_KEY not configured — emails will not be sent.', file=sys.stderr, flush=True)
            logger.error('RESEND_API_KEY not configured')
            return 0

        # Use RESEND_FROM_EMAIL when set; otherwise fall back to DEFAULT_FROM_EMAIL.
        # IMPORTANT: must be a verified sender/domain in the Resend dashboard.
        resend_from = getattr(settings, 'RESEND_FROM_EMAIL', None) or getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@tennis.app.br')

        sent = 0
        for message in email_messages:
            try:
                from_address = resend_from or message.from_email or settings.DEFAULT_FROM_EMAIL

                params = {
                    'from': from_address,
                    'to': list(message.to),
                    'subject': message.subject,
                }

                has_html = False
                for content, mimetype in (message.alternatives if hasattr(message, 'alternatives') else []):
                    if mimetype == 'text/html':
                        params['html'] = content
                        has_html = True
                    elif mimetype == 'text/plain':
                        params['text'] = content

                if not has_html:
                    if message.content_subtype == 'html':
                        params['html'] = message.body
                    else:
                        params['text'] = message.body

                if message.cc:
                    params['cc'] = list(message.cc)
                if message.bcc:
                    params['bcc'] = list(message.bcc)
                if message.reply_to:
                    params['reply_to'] = list(message.reply_to)

                result = resend.Emails.send(params)
                email_id = getattr(result, 'id', None) or (result.get('id') if isinstance(result, dict) else None)
                print(f'[EMAIL] Sent to {message.to} | subject="{message.subject}" | resend_id={email_id}', flush=True)
                logger.info('Email sent via Resend to %s, id=%s', message.to, email_id)
                sent += 1

            except Exception as exc:
                print(f'[EMAIL] FAILED to send to {message.to}: {exc}', file=sys.stderr, flush=True)
                print(f'[EMAIL] from="{from_address}" — If domain is not verified in Resend, set RESEND_FROM_EMAIL=onboarding@resend.dev in Railway env vars.', file=sys.stderr, flush=True)
                logger.exception('Resend failed to send email to %s: %s', message.to, exc)
                if not self.fail_silently:
                    raise
        return sent
