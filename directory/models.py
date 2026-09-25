from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction, connection
import phonenumbers
import random
import secrets


def lock_extension_namespace():
    # Extensions span five model tables and may be shared only by the same owner.
    # Serialize allocation AND validation across parent and staff writes.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [0x46504F524348])


def new_family_invite_code():
    return secrets.token_urlsafe(18)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Family(TimeStampedModel):
    name = models.CharField(max_length=200, unique=True)
    notes = models.TextField(blank=True)
    directory_listed = models.BooleanField(default=False)
    invite_code = models.CharField(
        max_length=32, unique=True, default=new_family_invite_code, editable=False
    )
    setup_dismissed = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "families"

    def __str__(self):
        return self.name


class Parent(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="frontporch_parent",
    )
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="parents")
    display_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=32, blank=True)
    dial_extension = models.CharField(max_length=4, unique=True, blank=True)
    call_destination = models.CharField(
        max_length=12,
        default="frontporch",
        choices=[
            ("frontporch", "FrontPorch phones"),
            ("phone", "My phone number"),
            ("both", "Both"),
            ("disabled", "Do not ring me"),
        ],
    )
    is_guardian = models.BooleanField(default=True)
    is_primary = models.BooleanField(default=False)
    directory_visible = models.BooleanField(default=False)
    emergency_notice_dismissed = models.BooleanField(default=False)

    class Meta:
        ordering = ["family__name", "display_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "display_name"],
                name="unique_parent_display_name_per_family",
            ),
            models.UniqueConstraint(
                fields=["family"],
                condition=models.Q(is_primary=True),
                name="one_primary_guardian_per_family",
            ),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.family})"

    @property
    def email(self):
        return self.user.email

    def clean(self):
        if self.phone:
            self.phone = ExternalPhoneNumber.normalize(self.phone)
        errors = {}
        if self.call_destination in {"phone", "both"} and not self.phone:
            errors["phone"] = "Enter a phone number or choose FrontPorch phones."
        if self.dial_extension:
            # Preserve existing three-digit parent extensions during the upgrade.
            if (
                not self.dial_extension.isascii()
                or not self.dial_extension.isdigit()
                or len(self.dial_extension) not in {3, 4}
                or ExternalNumberExtension._extension_is_reserved(self.dial_extension)
            ):
                errors["dial_extension"] = (
                    "Use a three- or four-digit non-reserved extension."
                )
            elif (
                Device.objects.filter(sip_extension=self.dial_extension)
                .exclude(pk__in=self.devices.values("pk") if self.pk else [])
                .exists()
                or ExternalNumberExtension.objects.filter(
                    dial_extension=self.dial_extension
                ).exists()
                or ChildLandline.objects.filter(
                    dial_extension=self.dial_extension, is_active=True
                ).exists()
                or ConferenceGroup.objects.filter(
                    dial_extension=self.dial_extension
                ).exists()
            ):
                errors["dial_extension"] = (
                    "This extension is already assigned to another destination."
                )
            if (
                self.pk
                and Parent.objects.filter(pk=self.pk)
                .exclude(dial_extension=self.dial_extension)
                .exists()
            ):
                errors["dial_extension"] = (
                    "A parent's calling extension cannot be changed."
                )
        if errors:
            raise ValidationError(errors)

    @transaction.atomic
    def save(self, *args, **kwargs):
        lock_extension_namespace()
        if not self.dial_extension:
            self.dial_extension = ExternalNumberExtension._assign_extension()
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def rings_frontporch(self):
        return self.call_destination in {"frontporch", "both"}

    @property
    def rings_phone(self):
        return self.call_destination in {"phone", "both"} and bool(self.phone)

    def has_call_destination(self, source=None):
        devices = self.devices.filter(is_active=True)
        if source is not None:
            devices = devices.exclude(pk=source.pk)
        return bool(self.rings_phone or (self.rings_frontporch and devices.exists()))


class Child(TimeStampedModel):
    family = models.ForeignKey(
        Family, on_delete=models.CASCADE, related_name="children"
    )
    name = models.CharField(max_length=200)
    color = models.CharField(
        max_length=10,
        default="yellow",
        choices=[
            ("yellow", "Yellow"),
            ("blue", "Blue"),
            ("lavender", "Lavender"),
            ("peach", "Peach"),
            ("green", "Green"),
        ],
    )
    spoken_name = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Optional pronunciation spelling used only for generated spoken menus. "
            "Leave blank to speak the child's name."
        ),
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["family__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "name"],
                name="unique_child_name_per_family",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.family})"

    @property
    def spoken_menu_name(self):
        return self.spoken_name.strip() or self.name


class ChildBlackoutPeriod(TimeStampedModel):
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"
    EVERY_DAY = "every_day"
    DAY_GROUP_CHOICES = [
        (WEEKDAYS, "Weekdays"),
        (WEEKENDS, "Weekends"),
        (EVERY_DAY, "Every day"),
    ]

    child = models.ForeignKey(
        Child,
        on_delete=models.CASCADE,
        related_name="blackout_periods",
    )
    label = models.CharField(max_length=200)
    day_group = models.CharField(max_length=20, choices=DAY_GROUP_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    approved_by = models.ForeignKey(
        Parent,
        on_delete=models.PROTECT,
        related_name="approved_child_blackout_periods",
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["child__family__name", "child__name", "day_group", "start_time"]

    def __str__(self):
        return f"{self.child} blackout {self.label}"

    @property
    def asterisk_days(self):
        return {
            self.WEEKDAYS: "mon-fri",
            self.WEEKENDS: "sat-sun",
            self.EVERY_DAY: "mon-sun",
        }[self.day_group]

    @property
    def asterisk_time_range(self):
        return f"{self.start_time:%H:%M}-{self.end_time:%H:%M}"

    def clean(self):
        errors = {}
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            errors["end_time"] = "End time must be after start time."
        if (
            self.approved_by_id
            and self.child_id
            and self.approved_by.family_id != self.child.family_id
        ):
            errors["approved_by"] = "Approval must come from the child's family."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Device(TimeStampedModel):
    assigned_child = models.ForeignKey(
        Child,
        on_delete=models.PROTECT,
        related_name="devices",
        null=True,
        blank=True,
    )
    assigned_parent = models.ForeignKey(
        Parent,
        on_delete=models.PROTECT,
        related_name="devices",
        null=True,
        blank=True,
    )
    assigned_family = models.ForeignKey(
        Family,
        on_delete=models.PROTECT,
        related_name="devices",
        null=True,
        blank=True,
    )
    friendly_name = models.CharField(max_length=200)
    sip_extension = models.CharField(
        max_length=32,
        db_index=True,
        help_text=(
            "Devices assigned to the same owner may share an extension while using "
            "separate SIP credentials."
        ),
    )
    sip_username = models.CharField(max_length=100, unique=True)
    sip_secret = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["friendly_name"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(assigned_child__isnull=False)
                        & models.Q(assigned_parent__isnull=True)
                        & models.Q(assigned_family__isnull=True)
                    )
                    | (
                        models.Q(assigned_child__isnull=True)
                        & models.Q(assigned_parent__isnull=False)
                        & models.Q(assigned_family__isnull=True)
                    )
                    | (
                        models.Q(assigned_child__isnull=True)
                        & models.Q(assigned_parent__isnull=True)
                        & models.Q(assigned_family__isnull=False)
                    )
                ),
                name="device_has_exactly_one_owner",
            ),
        ]

    def __str__(self):
        return f"{self.friendly_name} for {self.owner_display_name}"

    @property
    def owner(self):
        return self.assigned_child or self.assigned_parent or self.assigned_family

    @property
    def owner_type(self):
        if self.assigned_child_id:
            return "child"
        if self.assigned_parent_id:
            return "parent"
        if self.assigned_family_id:
            return "family"
        return ""

    @property
    def owner_display_name(self):
        owner = self.owner
        return str(owner) if owner else "unassigned"

    @property
    def owning_family(self):
        if self.assigned_child_id:
            return self.assigned_child.family
        if self.assigned_parent_id:
            return self.assigned_parent.family
        return self.assigned_family

    def clean(self):
        errors = {}
        owner_count = sum(
            owner is not None
            for owner in (
                self.assigned_child,
                self.assigned_parent,
                self.assigned_family,
            )
        )
        if owner_count != 1:
            errors["__all__"] = (
                "Device must be assigned to exactly one child, parent, or family."
            )
        elif self.sip_extension:
            devices_with_extension = Device.objects.filter(
                sip_extension=self.sip_extension
            ).exclude(pk=self.pk)
            owner_fields = (
                "assigned_child_id",
                "assigned_parent_id",
                "assigned_family_id",
            )
            owner_identity = tuple(getattr(self, field) for field in owner_fields)
            if any(
                tuple(getattr(device, field) for field in owner_fields)
                != owner_identity
                for device in devices_with_extension.only(*owner_fields)
            ):
                errors["sip_extension"] = (
                    "This extension is already assigned to a different child, parent, "
                    "or family."
                )
        if (
            self.sip_extension
            and "ExternalNumberExtension" in globals()
            and ExternalNumberExtension.objects.filter(
                dial_extension=self.sip_extension
            ).exists()
        ):
            errors["sip_extension"] = (
                "This extension is already assigned to an external number."
            )
        if (
            self.sip_extension
            and "ChildLandline" in globals()
            and ChildLandline.objects.filter(
                dial_extension=self.sip_extension,
                is_active=True,
            ).exists()
        ):
            errors["sip_extension"] = (
                "This extension is already assigned to a child landline."
            )
        if (
            self.sip_extension
            and "ConferenceGroup" in globals()
            and ConferenceGroup.objects.filter(
                dial_extension=self.sip_extension,
            ).exists()
        ):
            errors["sip_extension"] = (
                "This extension is already assigned to a conference group."
            )
        if self.sip_extension:
            if (
                Parent.objects.filter(dial_extension=self.sip_extension)
                .exclude(pk=self.assigned_parent_id)
                .exists()
            ):
                errors["sip_extension"] = (
                    "This extension is already assigned to a parent."
                )
            if (
                self.assigned_parent_id
                and not Parent.objects.filter(
                    pk=self.assigned_parent_id, dial_extension=self.sip_extension
                ).exists()
            ):
                errors["sip_extension"] = "Use the assigned parent's calling extension."
        if errors:
            raise ValidationError(errors)

    @transaction.atomic
    def save(self, *args, **kwargs):
        lock_extension_namespace()
        if self.assigned_parent_id and not self.sip_extension:
            self.sip_extension = Parent.objects.values_list(
                "dial_extension", flat=True
            ).get(pk=self.assigned_parent_id)
        self.full_clean()
        super().save(*args, **kwargs)


class ExternalPhoneNumberManager(models.Manager):
    def get_or_create_normalized(self, raw_number, region=None):
        normalized_number = self.model.normalize(raw_number, region=region)
        return self.get_or_create(normalized_number=normalized_number)


class ExternalPhoneNumber(TimeStampedModel):
    normalized_number = models.CharField(max_length=32, unique=True)

    objects = ExternalPhoneNumberManager()

    class Meta:
        ordering = ["normalized_number"]

    def __str__(self):
        return self.normalized_number

    @classmethod
    def normalize(cls, raw_number, region=None):
        if not raw_number or not str(raw_number).strip():
            raise ValidationError("Phone number is required.")

        default_region = region or getattr(settings, "DEFAULT_PHONE_REGION", "US")
        try:
            parsed = phonenumbers.parse(str(raw_number), default_region)
        except phonenumbers.NumberParseException as exc:
            raise ValidationError("Enter a valid phone number.") from exc

        if not phonenumbers.is_valid_number(parsed):
            raise ValidationError("Enter a valid phone number.")

        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    def clean(self):
        self.normalized_number = self.normalize(self.normalized_number)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


def _random_four_digit_extension():
    return str(random.SystemRandom().randint(1000, 9999))


class PublicPhoneNumber(TimeStampedModel):
    normalized_number = models.CharField(max_length=32, unique=True)
    label = models.CharField(max_length=200, blank=True)
    assigned_family = models.ForeignKey(
        Family,
        on_delete=models.PROTECT,
        related_name="public_phone_numbers",
        null=True,
        blank=True,
        help_text="Leave blank for a shared neighborhood number.",
    )
    provider_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["normalized_number"]

    def __str__(self):
        owner = self.assigned_family or "Shared"
        label = f"{self.label} " if self.label else ""
        return f"{label}{self.normalized_number} ({owner})"

    @property
    def is_shared(self):
        return self.assigned_family_id is None

    def clean(self):
        self.normalized_number = ExternalPhoneNumber.normalize(self.normalized_number)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ExternalNumberExtension(TimeStampedModel):
    external_phone_number = models.OneToOneField(
        ExternalPhoneNumber,
        on_delete=models.PROTECT,
        related_name="dialable_extension",
    )
    dial_extension = models.CharField(max_length=4, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["dial_extension"]

    def __str__(self):
        contact_labels = list(
            self.external_phone_number.family_contacts.select_related("family")
            .order_by("family__name", "label")
            .values_list("label", "family__name")[:3]
        )
        label_text = ", ".join(
            f"{label} ({family_name})" for label, family_name in contact_labels
        )
        if label_text:
            return (
                f"{self.dial_extension} -> {self.external_phone_number} [{label_text}]"
            )
        return f"{self.dial_extension} -> {self.external_phone_number}"

    def clean(self):
        errors = {}
        if self.dial_extension:
            if not self.dial_extension.isdigit() or len(self.dial_extension) != 4:
                errors["dial_extension"] = (
                    "External number extension must be four digits."
                )
            elif self._extension_is_reserved(self.dial_extension):
                errors["dial_extension"] = "This extension is reserved."
            elif Parent.objects.filter(dial_extension=self.dial_extension).exists():
                errors["dial_extension"] = (
                    "This extension is already assigned to a parent."
                )
            elif Device.objects.filter(sip_extension=self.dial_extension).exists():
                errors["dial_extension"] = (
                    "This extension is already assigned to a device."
                )
            elif (
                "ChildLandline" in globals()
                and ChildLandline.objects.filter(
                    dial_extension=self.dial_extension,
                    is_active=True,
                ).exists()
            ):
                errors["dial_extension"] = (
                    "This extension is already assigned to a child landline."
                )
            elif (
                ExternalNumberExtension.objects.filter(
                    dial_extension=self.dial_extension
                )
                .exclude(pk=self.pk)
                .exists()
            ):
                errors["dial_extension"] = (
                    "This extension is already assigned to an external number."
                )
            elif (
                "ConferenceGroup" in globals()
                and ConferenceGroup.objects.filter(
                    dial_extension=self.dial_extension,
                ).exists()
            ):
                errors["dial_extension"] = (
                    "This extension is already assigned to a conference group."
                )
        if errors:
            raise ValidationError(errors)

    @transaction.atomic
    def save(self, *args, **kwargs):
        lock_extension_namespace()
        if not self.dial_extension:
            self.dial_extension = self._assign_extension()
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def _extension_is_reserved(cls, extension):
        return extension in {"100", "911", "2", "3", "4", "5", "6", "7", "8", "9"}

    @classmethod
    def _assign_extension(cls):
        for _ in range(100):
            candidate = _random_four_digit_extension()
            if cls._extension_is_reserved(candidate):
                continue
            if Parent.objects.filter(dial_extension=candidate).exists():
                continue
            if Device.objects.filter(sip_extension=candidate).exists():
                continue
            if cls.objects.filter(dial_extension=candidate).exists():
                continue
            if (
                "ChildLandline" in globals()
                and ChildLandline.objects.filter(
                    dial_extension=candidate,
                    is_active=True,
                ).exists()
            ):
                continue
            if (
                "ConferenceGroup" in globals()
                and ConferenceGroup.objects.filter(dial_extension=candidate).exists()
            ):
                continue
            return candidate
        raise ValidationError("Could not assign an unused external number extension.")


class ChildLandline(TimeStampedModel):
    child = models.ForeignKey(
        Child,
        on_delete=models.CASCADE,
        related_name="landlines",
    )
    external_phone_number = models.ForeignKey(
        ExternalPhoneNumber,
        on_delete=models.PROTECT,
        related_name="child_landlines",
    )
    dial_extension = models.CharField(max_length=4, unique=True, blank=True)
    approved_by = models.ForeignKey(
        Parent,
        on_delete=models.PROTECT,
        related_name="approved_child_landlines",
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["child__family__name", "child__name", "dial_extension"]
        constraints = [
            models.UniqueConstraint(
                fields=["child"],
                condition=models.Q(is_active=True),
                name="unique_active_landline_per_child",
            ),
            models.UniqueConstraint(
                fields=["external_phone_number"],
                condition=models.Q(is_active=True),
                name="unique_active_child_landline_number",
            ),
        ]

    def __str__(self):
        return f"{self.child} landline at {self.dial_extension}"

    def clean(self):
        errors = {}
        if (
            self.approved_by_id
            and self.child_id
            and self.approved_by.family_id != self.child.family_id
        ):
            errors["approved_by"] = "Approval must come from the child's family."
        if self.dial_extension:
            if not self.dial_extension.isdigit() or len(self.dial_extension) != 4:
                errors["dial_extension"] = (
                    "Child landline extension must be four digits."
                )
            elif ExternalNumberExtension._extension_is_reserved(self.dial_extension):
                errors["dial_extension"] = "This extension is reserved."
            elif Parent.objects.filter(dial_extension=self.dial_extension).exists():
                errors["dial_extension"] = (
                    "This extension is already assigned to a parent."
                )
            elif Device.objects.filter(sip_extension=self.dial_extension).exists():
                errors["dial_extension"] = (
                    "This extension is already assigned to a device."
                )
            elif ExternalNumberExtension.objects.filter(
                dial_extension=self.dial_extension
            ).exists():
                errors["dial_extension"] = (
                    "This extension is already assigned to an external number."
                )
            elif (
                ChildLandline.objects.filter(
                    dial_extension=self.dial_extension,
                    is_active=True,
                )
                .exclude(pk=self.pk)
                .exists()
            ):
                errors["dial_extension"] = (
                    "This extension is already assigned to a child landline."
                )
            elif (
                "ConferenceGroup" in globals()
                and ConferenceGroup.objects.filter(
                    dial_extension=self.dial_extension,
                ).exists()
            ):
                errors["dial_extension"] = (
                    "This extension is already assigned to a conference group."
                )
        if errors:
            raise ValidationError(errors)

    @transaction.atomic
    def save(self, *args, **kwargs):
        lock_extension_namespace()
        if not self.dial_extension:
            self.dial_extension = self._assign_extension()
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def _assign_extension(cls):
        for _ in range(100):
            candidate = _random_four_digit_extension()
            if ExternalNumberExtension._extension_is_reserved(candidate):
                continue
            if Parent.objects.filter(dial_extension=candidate).exists():
                continue
            if Device.objects.filter(sip_extension=candidate).exists():
                continue
            if ExternalNumberExtension.objects.filter(
                dial_extension=candidate
            ).exists():
                continue
            if cls.objects.filter(dial_extension=candidate, is_active=True).exists():
                continue
            if (
                "ConferenceGroup" in globals()
                and ConferenceGroup.objects.filter(dial_extension=candidate).exists()
            ):
                continue
            return candidate
        raise ValidationError("Could not assign an unused child landline extension.")


class FamilyContact(TimeStampedModel):
    family = models.ForeignKey(
        Family, on_delete=models.CASCADE, related_name="contacts"
    )
    external_phone_number = models.ForeignKey(
        ExternalPhoneNumber,
        on_delete=models.PROTECT,
        related_name="family_contacts",
    )
    label = models.CharField(max_length=200)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["family__name", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "external_phone_number"],
                name="unique_contact_number_per_family",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.external_phone_number}, {self.family})"

    @property
    def dial_extension(self):
        return getattr(self.external_phone_number, "dialable_extension", None)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        ExternalNumberExtension.objects.get_or_create(
            external_phone_number=self.external_phone_number
        )


class ExternalContactPermission(TimeStampedModel):
    child = models.ForeignKey(
        Child,
        on_delete=models.CASCADE,
        related_name="external_contact_permissions",
    )
    external_phone_number = models.ForeignKey(
        ExternalPhoneNumber,
        on_delete=models.PROTECT,
        related_name="child_contact_permissions",
    )
    approved_by = models.ForeignKey(
        Parent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_external_contact_permissions",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["child__family__name", "child__name", "external_phone_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["child", "external_phone_number"],
                name="unique_external_contact_permission_per_child",
            ),
        ]

    def __str__(self):
        return f"{self.child} may communicate with {self.external_phone_number}"

    @property
    def is_active(self):
        return bool(self.approved_by_id)

    def clean(self):
        errors = {}
        if (
            self.approved_by_id
            and self.child_id
            and self.approved_by.family_id != self.child.family_id
        ):
            errors["approved_by"] = "Approval must come from the child's family."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class DialShortcut(TimeStampedModel):
    source_device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="dial_shortcuts",
    )
    digits = models.CharField(max_length=1)
    internal_target_device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="targeted_by_shortcuts",
        null=True,
        blank=True,
    )
    external_target_extension = models.ForeignKey(
        ExternalNumberExtension,
        on_delete=models.CASCADE,
        related_name="targeted_by_shortcuts",
        null=True,
        blank=True,
    )
    parent_target = models.ForeignKey(
        Parent,
        on_delete=models.CASCADE,
        related_name="targeted_by_shortcuts",
        null=True,
        blank=True,
    )
    child_landline_target = models.ForeignKey(
        ChildLandline,
        on_delete=models.CASCADE,
        related_name="targeted_by_shortcuts",
        null=True,
        blank=True,
    )
    conference_group_target = models.ForeignKey(
        "ConferenceGroup",
        on_delete=models.CASCADE,
        related_name="targeted_by_shortcuts",
        null=True,
        blank=True,
    )
    label = models.CharField(max_length=200, blank=True)
    approved_by = models.ForeignKey(
        Parent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_dial_shortcuts",
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["source_device__friendly_name", "digits"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_device", "digits"],
                name="unique_shortcut_digits_per_source_device",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(internal_target_device__isnull=False)
                        & models.Q(external_target_extension__isnull=True)
                        & models.Q(parent_target__isnull=True)
                        & models.Q(child_landline_target__isnull=True)
                        & models.Q(conference_group_target__isnull=True)
                    )
                    | (
                        models.Q(internal_target_device__isnull=True)
                        & models.Q(external_target_extension__isnull=False)
                        & models.Q(parent_target__isnull=True)
                        & models.Q(child_landline_target__isnull=True)
                        & models.Q(conference_group_target__isnull=True)
                    )
                    | (
                        models.Q(internal_target_device__isnull=True)
                        & models.Q(external_target_extension__isnull=True)
                        & models.Q(parent_target__isnull=False)
                        & models.Q(child_landline_target__isnull=True)
                        & models.Q(conference_group_target__isnull=True)
                    )
                    | (
                        models.Q(internal_target_device__isnull=True)
                        & models.Q(external_target_extension__isnull=True)
                        & models.Q(parent_target__isnull=True)
                        & models.Q(child_landline_target__isnull=False)
                        & models.Q(conference_group_target__isnull=True)
                    )
                    | (
                        models.Q(internal_target_device__isnull=True)
                        & models.Q(external_target_extension__isnull=True)
                        & models.Q(parent_target__isnull=True)
                        & models.Q(child_landline_target__isnull=True)
                        & models.Q(conference_group_target__isnull=False)
                    )
                ),
                name="dial_shortcut_has_exactly_one_target",
            ),
        ]

    def __str__(self):
        return f"{self.source_device} dials {self.digits}"

    def clean(self):
        if (
            self.internal_target_device_id
            and self.internal_target_device.assigned_parent_id
        ):
            if not self.parent_target_id:
                self.parent_target = self.internal_target_device.assigned_parent
                self.internal_target_device = None
        errors = {}
        if self.digits not in {"1", "2", "3", "4", "5", "6", "7", "8", "9"}:
            errors["digits"] = "Shortcut digits must be one of 1 through 9."

        target_count = sum(
            target is not None
            for target in (
                self.internal_target_device,
                self.external_target_extension,
                self.parent_target,
                self.child_landline_target,
                self.conference_group_target,
            )
        )
        if target_count != 1:
            errors["internal_target_device"] = "Shortcut must have exactly one target."

        if self.source_device_id:
            if (
                self.approved_by_id
                and self.approved_by.family_id != self.source_device.owning_family.id
            ):
                errors["approved_by"] = (
                    "Approval must come from the source device's family."
                )
            if self.internal_target_device_id and not _devices_may_call(
                self.source_device,
                self.internal_target_device,
            ):
                errors["internal_target_device"] = (
                    "Source device is not allowed to call this target device."
                )
            if self.external_target_extension_id and not _device_may_call_external(
                self.source_device,
                self.external_target_extension,
            ):
                errors["external_target_extension"] = (
                    "Source device is not allowed to call this external number."
                )
            if self.parent_target_id and not _device_may_call_parent(
                self.source_device,
                self.parent_target,
            ):
                errors["parent_target"] = (
                    "Source device is not allowed to call this parent phone."
                )
            if self.child_landline_target_id and not _device_may_call_child_landline(
                self.source_device,
                self.child_landline_target,
            ):
                errors["child_landline_target"] = (
                    "Source device is not allowed to call this child landline."
                )
            if self.conference_group_target_id:
                group = self.conference_group_target
                source_child_id = self.source_device.assigned_child_id
                if (
                    not group.is_active
                    or not group.calling_enabled
                    or not group.dial_extension
                    or group.members.count() < 2
                ):
                    errors["conference_group_target"] = (
                        "Conference group must be active and dialable."
                    )
                elif (
                    not source_child_id
                    or not group.members.filter(id=source_child_id).exists()
                ):
                    errors["conference_group_target"] = (
                        "Source device's child must be a member of this conference group."
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ChildLandlineDialShortcut(TimeStampedModel):
    source_landline = models.ForeignKey(
        ChildLandline,
        on_delete=models.CASCADE,
        related_name="dial_shortcuts",
    )
    digits = models.CharField(max_length=1)
    target_child = models.ForeignKey(
        Child,
        on_delete=models.CASCADE,
        related_name="targeted_by_landline_shortcuts",
    )
    approved_by = models.ForeignKey(
        Parent,
        on_delete=models.PROTECT,
        related_name="approved_child_landline_dial_shortcuts",
    )
    label = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = [
            "source_landline__child__family__name",
            "source_landline__child__name",
            "digits",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_landline", "digits"],
                name="unique_digits_per_child_landline",
            ),
            models.UniqueConstraint(
                fields=["source_landline", "target_child"],
                name="unique_target_per_child_landline",
            ),
        ]

    def __str__(self):
        return f"{self.source_landline} dials {self.digits} for {self.target_child}"

    def clean(self):
        errors = {}
        if self.digits not in {"1", "2", "3", "4", "5", "6", "7", "8", "9"}:
            errors["digits"] = "Shortcut digits must be one of 1 through 9."

        if self.source_landline_id:
            if self.is_active and not self.source_landline.is_active:
                errors["source_landline"] = "Source child landline must be active."
            if (
                self.approved_by_id
                and self.approved_by.family_id != self.source_landline.child.family_id
            ):
                errors["approved_by"] = (
                    "Approval must come from the source child landline's family."
                )
            if self.target_child_id:
                if self.target_child_id == self.source_landline.child_id:
                    errors["target_child"] = (
                        "A child landline cannot target its own child."
                    )
                elif self.is_active and not _children_may_call(
                    self.source_landline.child,
                    self.target_child,
                ):
                    errors["target_child"] = (
                        "The children do not have current reciprocal call permission."
                    )

        if (
            self.is_active
            and self.target_child_id
            and not (
                Device.objects.filter(
                    assigned_child_id=self.target_child_id,
                    is_active=True,
                ).exists()
                or ChildLandline.objects.filter(
                    child_id=self.target_child_id,
                    is_active=True,
                ).exists()
            )
        ):
            errors["target_child"] = "Target child has no active routable phone."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


def _devices_may_call(source, target):
    if source.pk == target.pk:
        return False
    if target.assigned_parent_id:
        return _device_may_call_parent(source, target.assigned_parent)
    if source.owning_family.pk == target.owning_family.pk:
        return True
    return bool(
        source.assigned_child_id
        and target.assigned_child_id
        and _children_may_call(source.assigned_child, target.assigned_child)
    )


def _children_may_call(source_child, target_child):
    if source_child.pk == target_child.pk:
        return False
    if source_child.family_id == target_child.family_id:
        return True
    child_a, child_b = sorted((source_child.pk, target_child.pk))
    return ChildConnection.objects.filter(
        child_a_id=child_a, child_b_id=child_b, is_active=True
    ).exists()


def _device_may_call_external(source, external_extension):
    if not source.assigned_child_id or not external_extension.is_active:
        return False
    if FamilyContact.objects.filter(
        family_id=source.owning_family.id,
        external_phone_number=external_extension.external_phone_number,
    ).exists():
        return True
    return ExternalContactPermission.objects.filter(
        child_id=source.assigned_child_id,
        external_phone_number=external_extension.external_phone_number,
        approved_by__isnull=False,
    ).exists()


def _device_may_call_parent(source, parent):
    return bool(
        parent.family_id == source.owning_family.id
        and parent.has_call_destination(source)
    )


def _device_may_call_child_landline(source, landline):
    if not landline.is_active:
        return False
    if source.owning_family.pk == landline.child.family_id:
        return True
    return bool(
        source.assigned_child_id
        and _children_may_call(source.assigned_child, landline.child)
    )


class ConferenceGroup(TimeStampedModel):
    name = models.CharField(max_length=200)
    members = models.ManyToManyField(Child, related_name="conference_groups")
    approved_by = models.ForeignKey(
        Parent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_conference_groups",
    )
    is_active = models.BooleanField(default=True)
    calling_enabled = models.BooleanField(
        default=False,
        help_text="Staff must enable calling before this group becomes dialable.",
    )
    dial_extension = models.CharField(
        max_length=4,
        unique=True,
        null=True,
        blank=True,
        help_text="Leave blank to assign an unused four-digit extension when enabled.",
    )
    ring_timeout_seconds = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(120)],
        help_text="How long unanswered member phones ring, from 5 to 120 seconds.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if self.dial_extension:
            if not self.dial_extension.isdigit() or len(self.dial_extension) != 4:
                errors["dial_extension"] = (
                    "Conference group extension must be four digits."
                )
            elif ExternalNumberExtension._extension_is_reserved(self.dial_extension):
                errors["dial_extension"] = "This extension is reserved."
            elif Parent.objects.filter(dial_extension=self.dial_extension).exists():
                errors["dial_extension"] = (
                    "This extension is already assigned to a parent."
                )
            elif Device.objects.filter(sip_extension=self.dial_extension).exists():
                errors["dial_extension"] = (
                    "This extension is already assigned to a device."
                )
            elif ExternalNumberExtension.objects.filter(
                dial_extension=self.dial_extension
            ).exists():
                errors["dial_extension"] = (
                    "This extension is already assigned to an external number."
                )
            elif ChildLandline.objects.filter(
                dial_extension=self.dial_extension,
            ).exists():
                errors["dial_extension"] = (
                    "This extension is already assigned to a child landline."
                )
            elif (
                ConferenceGroup.objects.filter(
                    dial_extension=self.dial_extension,
                )
                .exclude(pk=self.pk)
                .exists()
            ):
                errors["dial_extension"] = (
                    "This extension is already assigned to a conference group."
                )
        if errors:
            raise ValidationError(errors)

    @transaction.atomic
    def save(self, *args, **kwargs):
        lock_extension_namespace()
        if self.calling_enabled and not self.dial_extension:
            self.dial_extension = self._assign_extension()
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def _assign_extension(cls):
        for _ in range(100):
            candidate = _random_four_digit_extension()
            if ExternalNumberExtension._extension_is_reserved(candidate):
                continue
            if Parent.objects.filter(dial_extension=candidate).exists():
                continue
            if Device.objects.filter(sip_extension=candidate).exists():
                continue
            if ExternalNumberExtension.objects.filter(
                dial_extension=candidate
            ).exists():
                continue
            if ChildLandline.objects.filter(dial_extension=candidate).exists():
                continue
            if cls.objects.filter(dial_extension=candidate).exists():
                continue
            return candidate
        raise ValidationError("Could not assign an unused conference group extension.")


class FamilyActivity(TimeStampedModel):
    """Family-scoped history; keep text free of credentials and invitation tokens."""

    family = models.ForeignKey(
        Family, on_delete=models.CASCADE, related_name="activity"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    description = models.CharField(max_length=500)

    class Meta:
        ordering = ["-created_at", "-pk"]


class ChildConnection(TimeStampedModel):
    """One reciprocal child pair, canonicalized by primary key."""

    child_a = models.ForeignKey(
        Child, on_delete=models.CASCADE, related_name="connections_as_a"
    )
    child_b = models.ForeignKey(
        Child, on_delete=models.CASCADE, related_name="connections_as_b"
    )
    approved_by_a = models.ForeignKey(
        Parent, on_delete=models.PROTECT, related_name="child_connections_as_a"
    )
    approved_by_b = models.ForeignKey(
        Parent, on_delete=models.PROTECT, related_name="child_connections_as_b"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["child_a", "child_b"], name="unique_child_connection"
            ),
            models.CheckConstraint(
                condition=models.Q(child_a__lt=models.F("child_b")),
                name="ordered_child_connection",
            ),
        ]

    def clean(self):
        if self.child_a_id and self.child_b_id:
            if (
                self.child_a_id >= self.child_b_id
                or self.child_a.family_id == self.child_b.family_id
            ):
                raise ValidationError(
                    "Connections need two different families and ordered child IDs."
                )
            if (
                self.approved_by_a_id
                and self.approved_by_a.family_id != self.child_a.family_id
            ):
                raise ValidationError(
                    "The first approval must come from the first child's family."
                )
            if (
                self.approved_by_b_id
                and self.approved_by_b.family_id != self.child_b.family_id
            ):
                raise ValidationError(
                    "The second approval must come from the second child's family."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ConnectionInvitation(TimeStampedModel):
    source_family = models.ForeignKey(
        Family, on_delete=models.CASCADE, related_name="sent_connection_invitations"
    )
    target_family = models.ForeignKey(
        Family, on_delete=models.CASCADE, related_name="received_connection_invitations"
    )
    sent_by = models.ForeignKey(
        Parent, on_delete=models.PROTECT, related_name="sent_connection_invitations"
    )
    source_children = models.ManyToManyField(
        Child, related_name="sent_connection_invitations"
    )
    accepted_children = models.ManyToManyField(
        Child, related_name="accepted_connection_invitations", blank=True
    )
    message = models.TextField(blank=True, max_length=1000)
    status = models.CharField(
        max_length=12,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("accepted", "Accepted"),
            ("declined", "Declined"),
            ("cancelled", "Cancelled"),
        ],
    )
    responded_by = models.ForeignKey(
        Parent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="answered_connection_invitations",
    )

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_family", "target_family"],
                condition=models.Q(status="pending"),
                name="one_pending_invitation_per_family_direction",
            )
        ]

    def clean(self):
        if self.source_family_id == self.target_family_id:
            raise ValidationError("Invite a family outside your own.")
        if self.sent_by_id and self.sent_by.family_id != self.source_family_id:
            raise ValidationError(
                "The inviting guardian must belong to the source family."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class FamilyInvitation(TimeStampedModel):
    """An existing family sponsors one new household, without granting calls."""

    family = models.ForeignKey(
        Family, on_delete=models.CASCADE, related_name="family_invitations"
    )
    invited_by = models.ForeignKey(
        Parent, on_delete=models.PROTECT, related_name="family_invitations_sent"
    )
    email = models.EmailField()
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    status = models.CharField(
        max_length=12,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("accepted", "Accepted"),
            ("cancelled", "Cancelled"),
            ("replaced", "Replaced"),
        ],
    )
    accepted_family = models.OneToOneField(
        Family,
        on_delete=models.SET_NULL,
        related_name="registration_invitation",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "email"],
                condition=models.Q(status="pending"),
                name="one_pending_family_invitation_per_email",
            )
        ]

    @property
    def available(self):
        from django.utils import timezone

        return (
            self.status == "pending"
            and self.expires_at > timezone.now()
            and self.invited_by.is_guardian
            and self.invited_by.family_id == self.family_id
            and self.invited_by.user_id is not None
            and self.invited_by.user.is_active
        )


class GuardianInvitation(TimeStampedModel):
    family = models.ForeignKey(
        Family, on_delete=models.CASCADE, related_name="guardian_invitations"
    )
    invited_by = models.ForeignKey(
        Parent, on_delete=models.PROTECT, related_name="guardian_invitations_sent"
    )
    display_name = models.CharField(max_length=200)
    email = models.EmailField()
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    status = models.CharField(
        max_length=12,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("accepted", "Accepted"),
            ("cancelled", "Cancelled"),
            ("replaced", "Replaced"),
        ],
    )

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "email"],
                condition=models.Q(status="pending"),
                name="one_pending_guardian_invitation_per_email",
            )
        ]

    @property
    def available(self):
        from django.utils import timezone

        return self.status == "pending" and self.expires_at > timezone.now()
