"""
Envio de push nativo via API de push do Expo.

Não precisamos lidar com chaves APNs/FCM no backend: o Expo cuida da entrega; aqui só
fazemos um POST para o serviço de push do Expo com os ExponentPushTokens. As credenciais
APNs/FCM ficam no EAS (build), nunca neste repositório.

Docs: https://docs.expo.dev/push-notifications/sending-notifications/
"""
import logging

import requests

logger = logging.getLogger('apps.alerts')

EXPO_PUSH_URL = 'https://exp.host/--/api/v2/push/send'
# Tokens cujo retorno indica que o dispositivo não recebe mais push (app desinstalado, etc).
# Devem ser removidos do banco para não tentar de novo.
_DEAD_TOKEN_ERRORS = {'DeviceNotRegistered'}


def send_expo_push_messages(tokens, title, body, data=None):
    """
    Envia uma notificação para a lista de tokens.

    Retorna (enviados, tokens_invalidos, erros_transitorios):
    - enviados: contagem de envios aceitos;
    - tokens_invalidos: tokens mortos (DeviceNotRegistered) a remover do banco;
    - erros_transitorios: falhas que podem ter sucesso depois (rede, rate limit) — a task
      usa essa lista para decidir reagendar (retry). Lista vazia = sem falha transitória.
    """
    tokens = [t for t in (tokens or []) if t]
    if not tokens:
        return 0, []

    messages = [
        {
            'to': token,
            'title': title,
            'body': body or '',
            'data': data or {},
            'sound': 'default',
            'channelId': 'default',
        }
        for token in tokens
    ]

    try:
        resp = requests.post(
            EXPO_PUSH_URL,
            json=messages,
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            timeout=10,
        )
        resp.raise_for_status()
        receipts = resp.json().get('data', [])
    except Exception as exc:  # noqa: BLE001 — rede/Expo instável não quebra o chamador,
        # mas é reportado como erro transitório para que a task possa reagendar (retry).
        logger.warning('Expo push request failed: %s', exc)
        return 0, [], [f'expo_request_failed: {str(exc)[:80]}']

    sent = 0
    invalid = []
    errors = []
    # A ordem dos receipts espelha a ordem das mensagens enviadas.
    for token, receipt in zip(tokens, receipts):
        if not isinstance(receipt, dict):
            continue
        if receipt.get('status') == 'ok':
            sent += 1
        else:
            err = (receipt.get('details') or {}).get('error', '')
            if err in _DEAD_TOKEN_ERRORS:
                invalid.append(token)  # token morto: remover, não retentar
            else:
                errors.append(err or 'expo_unknown_error')  # transitório (ex.: rate limit)
            logger.warning('Expo push rejected for a token: %s', err or receipt)

    return sent, invalid, errors
