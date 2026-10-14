from django.core.cache import caches
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Place, Trip, Visit


@receiver(post_save, sender=Visit)
@receiver(post_delete, sender=Visit)
def invalidate_user_statistics(sender, instance, **kwargs):
    key = f"user:{instance.user_id}"
    transaction.on_commit(lambda: caches["statistics"].delete(key))


@receiver(post_save, sender=Trip)
@receiver(post_delete, sender=Trip)
@receiver(post_save, sender=Place)
@receiver(post_delete, sender=Place)
def invalidate_location_statistics(sender, **kwargs):
    transaction.on_commit(lambda: caches["statistics"].clear())
