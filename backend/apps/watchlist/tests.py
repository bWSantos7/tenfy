"""Tests for watchlist: summary active_registrations counts by user_status, not deadline."""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


def make_user(email='wl@example.com', password='pass123'):
    return User.objects.create_user(email=email, password=password, full_name='WL User')


def make_edition(title='WL Test Edition', org_name='Test Org WL', city='São Paulo', state='SP'):
    from apps.sources.models import Organization
    from apps.tournaments.models import Tournament, TournamentEdition, Venue
    org, _ = Organization.objects.get_or_create(name=org_name, defaults={'type': 'federation'})
    tournament = Tournament.objects.create(canonical_name=title, organization=org)
    venue = Venue.objects.create(city=city, state=state)
    return TournamentEdition.objects.create(
        tournament=tournament,
        title=title,
        venue=venue,
        is_published=True,
        season_year=2026,
    )


class WatchlistSummaryTestCase(TestCase):
    """summary endpoint active_registrations must count by user_status='registered_declared'."""

    def setUp(self):
        self.client = APIClient()
        self.user = make_user()
        self.client.force_authenticate(user=self.user)

    def test_summary_requires_auth(self):
        anon = APIClient()
        res = anon.get('/api/watchlist/summary/')
        self.assertEqual(res.status_code, 401)

    def test_summary_empty(self):
        res = self.client.get('/api/watchlist/summary/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['total'], 0)
        self.assertEqual(res.data['active_registrations'], 0)

    def test_active_registrations_counts_registered_status(self):
        from apps.watchlist.models import WatchlistItem
        edition = make_edition('WL Edition A', 'Org A')
        WatchlistItem.objects.create(
            user=self.user,
            edition=edition,
            user_status=WatchlistItem.STATUS_REGISTERED,
        )
        res = self.client.get('/api/watchlist/summary/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['total'], 1)
        self.assertEqual(res.data['active_registrations'], 1)

    def test_active_registrations_ignores_other_statuses(self):
        from apps.watchlist.models import WatchlistItem
        edition = make_edition('WL Edition B', 'Org B', city='Rio de Janeiro', state='RJ')
        WatchlistItem.objects.create(
            user=self.user,
            edition=edition,
            user_status=WatchlistItem.STATUS_NONE,
        )
        res = self.client.get('/api/watchlist/summary/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['active_registrations'], 0)
