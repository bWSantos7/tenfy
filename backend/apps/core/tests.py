import hashlib
from datetime import date, datetime
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.core import utils
from apps.core.pagination import StandardPagination
from apps.core.permissions import (
    IsAdmin, IsAdminOrReadOnly, IsSuperUser,
)
from apps.core.throttles import HeavyAnonThrottle, HeavyUserThrottle


def _req(method='GET', *, auth=True, staff=False, superuser=False):
    """Request falso o suficiente para as checagens de permissão."""
    user = SimpleNamespace(
        is_authenticated=auth, is_staff=staff, is_superuser=superuser)
    return SimpleNamespace(method=method, user=user)


class UtilsTests(SimpleTestCase):
    def test_compute_content_hash(self):
        self.assertEqual(utils.compute_content_hash(None), '')
        self.assertEqual(
            utils.compute_content_hash('abc'),
            hashlib.sha256('abc'.encode()).hexdigest())
        # determinístico
        self.assertEqual(
            utils.compute_content_hash('x'), utils.compute_content_hash('x'))

    def test_compute_sporting_age(self):
        self.assertEqual(utils.compute_sporting_age(2010, 2026), 16)
        self.assertEqual(utils.compute_sporting_age(2000, 2026), 26)
        # sem reference_year usa o ano corrente
        self.assertEqual(
            utils.compute_sporting_age(datetime.now().year), 0)

    def test_safe_get(self):
        d = {'a': {'b': {'c': 1}}}
        self.assertEqual(utils.safe_get(d, 'a', 'b', 'c'), 1)
        self.assertIsNone(utils.safe_get(d, 'a', 'x'))
        self.assertEqual(utils.safe_get(d, 'a', 'x', default='z'), 'z')
        self.assertEqual(utils.safe_get(d, 'a', 'b', 'c', 'd', default='z'), 'z')

    def test_diff_dicts(self):
        old = {'a': 1, 'b': 2, 'c': 3}
        new = {'a': 1, 'b': 9, 'd': 4}
        diff = utils.diff_dicts(old, new)
        self.assertEqual(diff['b'], {'old': 2, 'new': 9})
        self.assertEqual(diff['c'], {'old': 3, 'new': None})  # removido
        self.assertEqual(diff['d'], {'old': None, 'new': 4})  # adicionado
        self.assertNotIn('a', diff)  # inalterado

    def test_to_iso(self):
        self.assertIsNone(utils.to_iso(None))
        self.assertEqual(utils.to_iso(date(2026, 7, 3)), '2026-07-03')
        self.assertTrue(utils.to_iso(datetime(2026, 7, 3, 10, 0)).startswith('2026-07-03T'))
        self.assertEqual(utils.to_iso(42), '42')


class PermissionsTests(SimpleTestCase):
    def test_is_admin(self):
        perm = IsAdmin()
        self.assertTrue(perm.has_permission(_req(staff=True), None))
        self.assertTrue(perm.has_permission(_req(superuser=True), None))
        self.assertFalse(perm.has_permission(_req(), None))          # user comum
        self.assertFalse(perm.has_permission(_req(auth=False), None))  # anônimo

    def test_is_admin_or_read_only(self):
        perm = IsAdminOrReadOnly()
        # leitura liberada para qualquer um (inclusive anônimo)
        self.assertTrue(perm.has_permission(_req('GET', auth=False), None))
        # escrita exige staff/superuser
        self.assertFalse(perm.has_permission(_req('POST'), None))
        self.assertTrue(perm.has_permission(_req('POST', staff=True), None))

    def test_is_superuser(self):
        perm = IsSuperUser()
        self.assertTrue(perm.has_permission(_req(superuser=True), None))
        self.assertFalse(perm.has_permission(_req(staff=True), None))


class ThrottlePaginationTests(SimpleTestCase):
    def test_throttle_scopes(self):
        self.assertEqual(HeavyUserThrottle.scope, 'heavy_user')
        self.assertEqual(HeavyAnonThrottle.scope, 'heavy_anon')

    def test_pagination_limits(self):
        p = StandardPagination()
        self.assertEqual(p.page_size, 20)
        self.assertEqual(p.max_page_size, 100)
        self.assertEqual(p.page_size_query_param, 'page_size')
