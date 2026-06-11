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

# (uf, name, short_name) — siglas oficiais no formato SIGLA-UF (task.md TASK 1).
# A UF é a chave autoritativa: siglas se repetem entre estados (FCT=CE/SC,
# FPT=SP/PA/PB/PR/RN, FBT=BA/DF, FMT=MA/MT), por isso nunca usar sigla solta.
BRAZIL_TENNIS_FEDERATIONS = [
    ('AC', 'Federação Acreana de Tênis', 'FAT-AC'),
    ('AL', 'Federação Alagoana de Tênis', 'FAT-AL'),
    ('AM', 'Federação Amazonense de Tênis', 'FAmT-AM'),
    ('AP', 'Federação Amapaense de Tênis', 'FAPT-AP'),
    ('BA', 'Federação Bahiana de Tênis', 'FBT-BA'),
    ('CE', 'Federação Cearense de Tênis', 'FCT-CE'),
    ('DF', 'Federação Brasiliense de Tênis', 'FBT-DF'),
    ('ES', 'Federação Espírito-Santense de Tênis', 'FEST-ES'),
    ('GO', 'Federação Goiana de Tênis', 'FGT-GO'),
    ('MA', 'Federação Maranhense de Tênis', 'FMT-MA'),
    ('MG', 'Federação Mineira de Tênis e Beach Tennis', 'FMTBT-MG'),
    ('MS', 'Federação Sul-Matogrossense de Tênis', 'FSMT-MS'),
    ('MT', 'Federação Mato-grossense de Tênis', 'FMT-MT'),
    ('PA', 'Federação Paraense de Tênis', 'FPT-PA'),
    ('PB', 'Federação Paraibana de Tênis', 'FPT-PB'),
    ('PE', 'Federação Pernambucana de Tênis', 'FPeT-PE'),
    ('PI', 'Federação de Tênis e Beach Tênis do Piauí', 'FTBTPI-PI'),
    ('PR', 'Federação Paranaense de Tênis', 'FPT-PR'),
    ('RJ', 'Associação Desportiva de Tênis do Estado do Rio de Janeiro', 'ADTERJ-RJ'),
    ('RN', 'Federação Potiguar de Tênis', 'FPT-RN'),
    ('RO', 'Federação Rondoniense de Tênis', 'FRT-RO'),
    ('RR', 'Federação Roraimense de Tênis e Beach Tennis', 'FRTBT-RR'),
    ('RS', 'Federação Gaúcha de Tênis', 'FGT-RS'),
    ('SC', 'Federação Catarinense de Tênis', 'FCT-SC'),
    ('SE', 'Federação Sergipana de Tênis', 'FST-SE'),
    ('SP', 'Federação Paulista de Tênis', 'FPT-SP'),
    ('TO', 'Federação Tocantinense de Tênis', 'FTT-TO'),
]
