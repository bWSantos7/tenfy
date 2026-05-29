import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimestampedModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimestampedModel):
    ROLE_PLAYER = 'player'
    ROLE_COACH = 'coach'
    ROLE_PARENT = 'parent'
    ROLE_ADMIN = 'admin'
    ROLE_CHOICES = [
        (ROLE_PLAYER, 'Jogador'),
        (ROLE_COACH, 'Treinador'),
        (ROLE_PARENT, 'Pai/Responsável'),
        (ROLE_ADMIN, 'Administrador'),
    ]

    email = models.EmailField(_('email address'), unique=True, db_index=True)
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True, help_text='Celular com DDD, ex: +5511999999999')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_PLAYER)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # Verification
    email_verified = models.BooleanField(default=False)

    # LGPD / consent
    consent_version = models.CharField(max_length=20, blank=True, default='')
    consented_at = models.DateTimeField(null=True, blank=True)
    marketing_consent = models.BooleanField(default=False)

    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.email

    def get_full_name(self):
        return self.full_name or self.email

    def get_short_name(self):
        return self.full_name.split(' ')[0] if self.full_name else self.email


class CoachAthlete(TimestampedModel):
    """Links a coach user to an athlete user they manage."""
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='athletes'
    )
    athlete = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='coaches'
    )
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['coach', 'athlete'], name='unique_coach_athlete'),
        ]

    def __str__(self):
        return f'{self.coach.email} -> {self.athlete.email}'


class ParentChild(TimestampedModel):
    """Links a parent/responsible account to a child player account."""
    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='children_links'
    )
    child = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='parent_links'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['parent', 'child'], name='unique_parent_child'),
        ]

    def __str__(self):
        return f'{self.parent.email} -> {self.child.email}'


def _invite_token():
    return f'inv_{uuid.uuid4().hex}'


def _invite_expires():
    return timezone.now() + timedelta(days=7)


class DependentInvite(TimestampedModel):
    """Consent-based invite: responsible asks an existing player to become their dependent."""
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_DECLINED = 'declined'
    STATUS_CANCELED = 'canceled'
    STATUS_EXPIRED = 'expired'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendente'),
        (STATUS_ACCEPTED, 'Aceito'),
        (STATUS_DECLINED, 'Recusado'),
        (STATUS_CANCELED, 'Cancelado'),
        (STATUS_EXPIRED, 'Expirado'),
    ]

    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='sent_dependent_invites',
    )
    invitee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='received_dependent_invites',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    token = models.CharField(max_length=64, unique=True, default=_invite_token, editable=False)
    expires_at = models.DateTimeField(default=_invite_expires)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['invitee', 'status']),
            models.Index(fields=['parent', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['parent', 'invitee'],
                condition=Q(status='pending'),
                name='unique_pending_dependent_invite',
            ),
        ]

    def is_expired(self) -> bool:
        return self.status == self.STATUS_PENDING and timezone.now() > self.expires_at

    def __str__(self):
        return f'DependentInvite({self.parent.email} -> {self.invitee.email}, {self.status})'
