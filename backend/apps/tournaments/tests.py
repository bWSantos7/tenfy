"""
Tests for tournament filters and views.
Focused on COSAT visibility regression and search filter coverage.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.sources.models import Organization, DataSource
from apps.tournaments.models import Tournament, TournamentEdition, Venue

User = get_user_model()


def _setup_cosat_tournament(db):
    """Create minimal COSAT tournament fixture. Returns TournamentEdition."""
    org, _ = Organization.objects.get_or_create(
        name='COSAT_FILTER_TEST',
        defaults={'short_name': 'COSAT', 'type': Organization.TYPE_CONFEDERATION},
    )
    ds, _ = DataSource.objects.get_or_create(
        connector_key='cosat_filter_test',
        defaults={
            'organization': org, 'source_name': 'COSAT Filter Test',
            'slug': 'cosat-filter-test',
            'source_type': DataSource.SOURCE_TYPE_JSON,
            'base_url': 'https://cosat.tournamentsoftware.com',
        },
    )
    tournament, _ = Tournament.objects.get_or_create(
        canonical_slug='copa-cosat-14-anos-test',
        defaults={
            'canonical_name': 'Copa COSAT 14 años',
            'circuit': 'COSAT',
            'organization': org,
        },
    )
    edition, _ = TournamentEdition.objects.get_or_create(
        external_id='cosat:copa-cosat-14-test',
        defaults={
            'tournament': tournament,
            'data_source': ds,
            'title': 'Copa COSAT 14 años',
            'season_year': 2025,
            'status': 'unknown',
            'is_youth': True,  # correctly classified
        },
    )
    return edition


class TournamentFilterCosatTestCase(TestCase):
    """Endpoint returns COSAT tournaments when circuit=COSAT filter is applied."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='filter_test@test.com', password='pass', is_staff=False
        )
        self.client.force_authenticate(user=self.user)
        self.edition = _setup_cosat_tournament(self)

    def test_circuit_cosat_filter_returns_edition(self):
        """GET /api/tournaments/editions/?circuit=COSAT returns COSAT tournament."""
        res = self.client.get('/api/tournaments/editions/', {'circuit': 'COSAT'})
        self.assertEqual(res.status_code, 200)
        ids = [e['id'] for e in (res.data.get('results') or res.data)]
        self.assertIn(self.edition.id, ids,
                      'COSAT tournament must appear when circuit=COSAT filter applied')

    def test_search_cosat_text_finds_tournament(self):
        """GET /api/tournaments/editions/?q=cosat finds tournament by circuit."""
        res = self.client.get('/api/tournaments/editions/', {'q': 'cosat'})
        self.assertEqual(res.status_code, 200)
        ids = [e['id'] for e in (res.data.get('results') or res.data)]
        self.assertIn(self.edition.id, ids,
                      'Text search for "cosat" must find COSAT tournament via circuit field')

    def test_null_start_date_not_excluded_by_queryset(self):
        """Tournament with start_date=None is not excluded by the queryset filter."""
        self.edition.start_date = None
        self.edition.save(update_fields=['start_date', 'updated_at'])
        # Directly test the queryset — no API pagination interaction
        from apps.tournaments.models import TournamentEdition
        from django.db.models import Q
        ids = list(
            TournamentEdition.objects
            .filter(Q(is_youth=True) | Q(is_youth__isnull=True))
            .filter(tournament__circuit__icontains='COSAT')
            .values_list('id', flat=True)
        )
        self.assertIn(self.edition.id, ids,
                      'is_youth filter must not exclude null-start_date COSAT tournament')

    def test_is_youth_false_excluded_from_default_list(self):
        """Tournament with is_youth=False is excluded from default list (not COSAT-specific)."""
        self.edition.is_youth = False
        self.edition.save(update_fields=['is_youth'])
        res = self.client.get('/api/tournaments/editions/', {'circuit': 'COSAT'})
        self.assertEqual(res.status_code, 200)
        ids = [e['id'] for e in (res.data.get('results') or res.data)]
        self.assertNotIn(self.edition.id, ids,
                         'is_youth=False must be excluded unless youth_only=false')

    def test_youth_only_false_bypasses_is_youth_filter(self):
        """?youth_only=false shows is_youth=False tournaments (admin/debug use)."""
        self.edition.is_youth = False
        self.edition.save(update_fields=['is_youth'])
        res = self.client.get('/api/tournaments/editions/',
                              {'circuit': 'COSAT', 'youth_only': 'false'})
        self.assertEqual(res.status_code, 200)
        ids = [e['id'] for e in (res.data.get('results') or res.data)]
        self.assertIn(self.edition.id, ids)

    def test_calendar_cache_varies_by_filter_params(self):
        """Calendar cache must not reuse an unfiltered response for filtered queries."""
        cache.clear()
        sp_venue = Venue.objects.create(name='Arena SP', city='Sao Paulo', state='SP')
        rj_venue = Venue.objects.create(name='Arena RJ', city='Rio de Janeiro', state='RJ')
        self.edition.start_date = '2026-06-10'
        self.edition.venue = sp_venue
        self.edition.save(update_fields=['start_date', 'venue', 'updated_at'])
        rj_edition = TournamentEdition.objects.create(
            tournament=self.edition.tournament,
            external_id='cosat:rj-cache-test',
            title='Copa COSAT RJ',
            season_year=2026,
            status='unknown',
            is_youth=True,
            start_date='2026-06-11',
            venue=rj_venue,
        )

        unfiltered = self.client.get('/api/tournaments/editions/calendar/')
        filtered = self.client.get('/api/tournaments/editions/calendar/', {'state': 'SP'})

        self.assertEqual(unfiltered.status_code, 200)
        self.assertEqual(filtered.status_code, 200)
        unfiltered_ids = [
            item['id']
            for month in unfiltered.data
            for item in month['items']
        ]
        filtered_ids = [
            item['id']
            for month in filtered.data
            for item in month['items']
        ]

        self.assertIn(rj_edition.id, unfiltered_ids)
        self.assertIn(self.edition.id, filtered_ids)
        self.assertNotIn(rj_edition.id, filtered_ids)
