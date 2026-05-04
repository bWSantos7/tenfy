"""Runs all seed commands in correct order."""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Seeds all reference data: categories, organizations, data sources.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('1/2 Seeding player categories...'))
        call_command('seed_player_categories')
        self.stdout.write(self.style.NOTICE('2/2 Seeding organizations and sources...'))
        call_command('seed_sources')
        self.stdout.write(self.style.SUCCESS('All seeds applied.'))
