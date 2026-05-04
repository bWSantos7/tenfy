"""
Post-save signal: when a PlayerProfile's home_city or home_state changes,
geocode the new location and persist home_lat/home_lng.
This avoids Nominatim calls at query time in within_profile_radius().
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PlayerProfile

logger = logging.getLogger('apps.players')


@receiver(post_save, sender=PlayerProfile)
def geocode_profile_home(sender, instance: PlayerProfile, created: bool, **kwargs):
    # Skip if coordinates are already set (avoid re-geocoding on unrelated saves)
    if instance.home_lat is not None and instance.home_lng is not None:
        return
    if not instance.home_city or not instance.home_state:
        return

    try:
        from apps.eligibility.location import geocode_and_save_profile
        updated = geocode_and_save_profile(instance)
        if updated:
            logger.info('Geocoded profile %s: (%.4f, %.4f)', instance.pk, instance.home_lat, instance.home_lng)
    except Exception as exc:
        logger.warning('Geocoding failed for profile %s: %s', instance.pk, exc)
