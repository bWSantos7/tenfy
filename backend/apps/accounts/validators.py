"""Validadores de senha customizados (Task 14)."""
import re

from django.core.exceptions import ValidationError


class StrongPasswordValidator:
    """Exige ao menos uma letra maiúscula, um número e um caractere especial.

    Combina com o MinimumLengthValidator(8) do Django para a regra completa:
    mínimo 8 caracteres, 1 maiúscula, 1 número e 1 caractere especial.
    """

    HELP = (
        'A senha deve ter no mínimo 8 caracteres, com ao menos uma letra '
        'maiúscula, um número e um caractere especial.'
    )

    def validate(self, password, user=None):
        faltas = []
        if not re.search(r'[A-Z]', password):
            faltas.append('uma letra maiúscula')
        if not re.search(r'\d', password):
            faltas.append('um número')
        if not re.search(r'[^A-Za-z0-9]', password):
            faltas.append('um caractere especial')
        if faltas:
            raise ValidationError(
                'A senha deve conter ' + ', '.join(faltas) + '.',
                code='password_not_strong',
            )

    def get_help_text(self):
        return self.HELP
