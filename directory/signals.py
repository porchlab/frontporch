from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from directory.asterisk.autoreload import schedule_asterisk_configuration_apply
from directory.models import (
    AllowedChildFamilyRelationship,
    Child,
    ChildConnection,
    ChildBlackoutPeriod,
    ChildLandline,
    ChildLandlineDialShortcut,
    ConferenceGroup,
    Device,
    DialShortcut,
    ExternalContactPermission,
    ExternalNumberExtension,
    ExternalPhoneNumber,
    Family,
    FamilyContact,
    Parent,
    PublicPhoneNumber,
)


@receiver(post_save, sender=ChildConnection)
@receiver(post_delete, sender=ChildConnection)
@receiver(post_save, sender=Family)
@receiver(post_save, sender=Parent)
@receiver(post_save, sender=Child)
@receiver(post_save, sender=ChildBlackoutPeriod)
@receiver(post_save, sender=ChildLandline)
@receiver(post_save, sender=ChildLandlineDialShortcut)
@receiver(post_save, sender=ConferenceGroup)
@receiver(post_save, sender=Device)
@receiver(post_save, sender=ExternalPhoneNumber)
@receiver(post_save, sender=ExternalNumberExtension)
@receiver(post_save, sender=FamilyContact)
@receiver(post_save, sender=PublicPhoneNumber)
@receiver(post_save, sender=AllowedChildFamilyRelationship)
@receiver(post_save, sender=ExternalContactPermission)
@receiver(post_save, sender=DialShortcut)
@receiver(post_delete, sender=Family)
@receiver(post_delete, sender=Parent)
@receiver(post_delete, sender=Child)
@receiver(post_delete, sender=ChildBlackoutPeriod)
@receiver(post_delete, sender=ChildLandline)
@receiver(post_delete, sender=ChildLandlineDialShortcut)
@receiver(post_delete, sender=ConferenceGroup)
@receiver(post_delete, sender=Device)
@receiver(post_delete, sender=ExternalPhoneNumber)
@receiver(post_delete, sender=ExternalNumberExtension)
@receiver(post_delete, sender=FamilyContact)
@receiver(post_delete, sender=PublicPhoneNumber)
@receiver(post_delete, sender=AllowedChildFamilyRelationship)
@receiver(post_delete, sender=ExternalContactPermission)
@receiver(post_delete, sender=DialShortcut)
def apply_asterisk_configuration_after_model_change(**kwargs):
    schedule_asterisk_configuration_apply()


@receiver(m2m_changed, sender=ConferenceGroup.members.through)
def apply_asterisk_configuration_after_conference_members_change(action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        schedule_asterisk_configuration_apply()
