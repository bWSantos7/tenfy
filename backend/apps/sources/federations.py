"""
Canonical registry of Brazilian state tennis federations (one per UF).

Used both by the `seed_organizations` management command and by the data
migration that seeds federations in every environment. The UF (`state`) is the
authoritative key: it links a PlayerProfile.federation to the eligibility engine.
Short names (acronyms) are display-only and intentionally disambiguated where
the conventional acronym collides between federations (e.g. FCT is used by both
the Carioca/RJ and Catarinense/SC federations).

Names follow the standard public naming convention for each state federation and
should be reviewed/confirmed by an admin against each federation's official site.
"""

# (uf, name, short_name)
BRAZIL_TENNIS_FEDERATIONS = [
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
