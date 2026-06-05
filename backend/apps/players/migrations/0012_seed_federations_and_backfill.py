"""
Seed the 27 Brazilian state tennis federations as Organization(type='federation')
and backfill existing PlayerProfiles' `federation` from their `home_state`.

Non-destructive: only fills federation where it is currently NULL and a federation
exists for the profile's home_state. The list is inlined (not imported from
apps.sources.federations) so this migration stays replayable even if that module
changes later.
"""
from django.db import migrations

# (uf, name, short_name) — mirror of apps.sources.federations.BRAZIL_TENNIS_FEDERATIONS
FEDERATIONS = [
    ('AC', 'Federação de Tênis do Acre', 'FTAC'),
    ('AL', 'Federação Alagoana de Tênis', 'FAT-AL'),
    ('AP', 'Federação Amapaense de Tênis', 'FAPT'),
    ('AM', 'Federação Amazonense de Tênis', 'FAT-AM'),
    ('BA', 'Federação Baiana de Tênis', 'FBT'),
    ('CE', 'Federação Cearense de Tênis', 'FCET'),
    ('DF', 'Federação de Tênis de Brasília', 'FTB'),
    ('ES', 'Federação de Tênis do Espírito Santo', 'FTES'),
    ('GO', 'Federação Goiana de Tênis', 'FGOT'),
    ('MA', 'Federação Maranhense de Tênis', 'FMAT'),
    ('MT', 'Federação Mato-grossense de Tênis', 'FTMT'),
    ('MS', 'Federação de Tênis de Mato Grosso do Sul', 'FTMS'),
    ('MG', 'Federação Mineira de Tênis', 'FMT'),
    ('PA', 'Federação Paraense de Tênis', 'FPAT'),
    ('PB', 'Federação Paraibana de Tênis', 'FPBT'),
    ('PR', 'Federação Paranaense de Tênis', 'FPRT'),
    ('PE', 'Federação Pernambucana de Tênis', 'FPET'),
    ('PI', 'Federação Piauiense de Tênis', 'FPIT'),
    ('RJ', 'Federação Carioca de Tênis', 'FCT'),
    ('RN', 'Federação Norte-rio-grandense de Tênis', 'FNRT'),
    ('RS', 'Federação Gaúcha de Tênis', 'FGT'),
    ('RO', 'Federação de Tênis de Rondônia', 'FTRO'),
    ('RR', 'Federação Roraimense de Tênis', 'FRRT'),
    ('SC', 'Federação Catarinense de Tênis', 'FCAT'),
    ('SP', 'Federação Paulista de Tênis', 'FPT'),
    ('SE', 'Federação Sergipana de Tênis', 'FSET'),
    ('TO', 'Federação Tocantinense de Tênis', 'FTOT'),
]


def seed_and_backfill(apps, schema_editor):
    Organization = apps.get_model('sources', 'Organization')
    PlayerProfile = apps.get_model('players', 'PlayerProfile')

    state_to_org = {}
    for uf, name, short in FEDERATIONS:
        org, created = Organization.objects.get_or_create(
            name=name,
            defaults={
                'short_name': short,
                'type': 'federation',
                'state': uf,
                'is_active': True,
            },
        )
        if not created:
            changed = False
            if org.state != uf:
                org.state = uf
                changed = True
            if org.type != 'federation':
                org.type = 'federation'
                changed = True
            if not org.short_name:
                org.short_name = short
                changed = True
            if changed:
                org.save()
        # Only the canonical federation should win the state slot.
        state_to_org.setdefault(uf, org)

    # Backfill: fill federation from home_state where not already set.
    for uf, org in state_to_org.items():
        PlayerProfile.objects.filter(
            federation__isnull=True, home_state__iexact=uf,
        ).update(federation=org)


def unset_federation(apps, schema_editor):
    """Reverse: only clears the FK we may have set; never deletes federations
    (they may be referenced elsewhere / be canonical reference data)."""
    PlayerProfile = apps.get_model('players', 'PlayerProfile')
    PlayerProfile.objects.update(federation=None)


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0011_playerprofile_federation_and_more'),
        ('sources', '0002_alter_datasource_connector_key'),
    ]

    operations = [
        migrations.RunPython(seed_and_backfill, unset_federation),
    ]
