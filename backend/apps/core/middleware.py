import logging
import time

logger = logging.getLogger('apps.core')


class RequestLoggingMiddleware:
    """Logs request duration and status for observability."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)
        duration_ms = int((time.time() - start) * 1000)
        if request.path.startswith('/api/'):
            logger.info(
                'request path=%s method=%s status=%s duration_ms=%d',
                request.path, request.method, response.status_code, duration_ms
            )
        return response
