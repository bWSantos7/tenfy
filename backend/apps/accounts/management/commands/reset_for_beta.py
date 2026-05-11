"""
Management command: reset_for_beta

Deletes ALL user accounts (and cascaded personal data) while preserving
tournament/source data, then creates a single master account.

Usage:
    python manage.py reset_for_beta
    python manage.py reset_for_beta --password MinhaSenha123!
    python manage.py reset_for_beta --no-confirm   # skip interactive prompt
"""
import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction


def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + '!@#$&'
    while True:
        pwd = ''.join(secrets.choice(alphabet) for _ in range(length))
        # Ensure at least one of each required character class
        if (any(c.islower() for c in pwd)
                and any(c.isupper() for c in pwd)
                and any(c.isdigit() for c in pwd)
                and any(c in '!@#$&' for c in pwd)):
            return pwd


class Command(BaseCommand):
    help = 'Reset all users for beta and create a single master account'

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            type=str,
            default=None,
            help='Password for the master account (generated if omitted)',
        )
        parser.add_argument(
            '--no-confirm',
            action='store_true',
            default=False,
            help='Skip the interactive confirmation prompt',
        )

    def handle(self, *args, **options):
        User = get_user_model()

        if not options['no_confirm']:
            self.stdout.write(
                self.style.WARNING(
                    '\n*** ATENÇÃO: Esta operação vai APAGAR TODOS os usuários do banco. ***\n'
                    'Torneios e dados de fontes serão preservados.\n'
                )
            )
            confirm = input('Digite CONFIRMAR para continuar: ').strip()
            if confirm != 'CONFIRMAR':
                self.stdout.write(self.style.ERROR('Operação cancelada.'))
                return

        password = options['password'] or _generate_password()
        master_email = 'brunowsantos15@gmail.com'

        with transaction.atomic():
            # Delete all users — cascades to profiles, watchlists, subscriptions, etc.
            deleted_count, _ = User.objects.all().delete()
            self.stdout.write(f'Removidos {deleted_count} registros de usuários e dados relacionados.')

            # Create master superuser
            user = User.objects.create_superuser(
                email=master_email,
                password=password,
                full_name='Bruno Santos',
                role='parent',
            )
            user.email_verified = True
            user.save(update_fields=['email_verified'])

            # Assign Tester plan subscription if it exists
            try:
                from apps.billing.models import Plan, Subscription
                from datetime import timedelta
                from django.utils import timezone

                tester_plan = Plan.objects.get(slug=Plan.SLUG_TESTER)
                Subscription.objects.create(
                    user=user,
                    plan=tester_plan,
                    status=Subscription.STATUS_ACTIVE,
                    billing_period='monthly',
                    start_date=timezone.localdate(),
                    next_due_date=timezone.localdate() + timedelta(days=365),
                )
                self.stdout.write(self.style.SUCCESS('Assinatura Tester criada para o master.'))
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(f'Assinatura Tester não criada: {exc}')
                )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 50))
        self.stdout.write(self.style.SUCCESS('Master account criado com sucesso!'))
        self.stdout.write(self.style.SUCCESS(f'  E-mail : {master_email}'))
        self.stdout.write(self.style.SUCCESS(f'  Senha  : {password}'))
        self.stdout.write(self.style.SUCCESS(f'  Role   : parent (responsável) + staff + superuser'))
        self.stdout.write(self.style.SUCCESS('=' * 50))
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('Guarde esta senha agora — ela não será exibida novamente.'))
