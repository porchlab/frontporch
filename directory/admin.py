from django.contrib import admin
from django import forms
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.contrib.auth.models import User
from django.views.decorators.debug import sensitive_variables

from .accounts import sync_account_email, validate_account_email

from .models import (
    Child,
    ChildConnection,
    GroupInvitation,
    ConnectionInvitation,
    GuardianInvitation,
    FamilyActivity,
    FamilyInvitation,
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
    WireGuardPeer,
)


class AccountEmailMixin:
    def clean_email(self):
        return validate_account_email(
            self.cleaned_data.get("email", ""), user_id=self.instance.pk
        )


class AccountCreationForm(AccountEmailMixin, AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        fields = ("username", "email")


class AccountChangeForm(AccountEmailMixin, UserChangeForm):
    pass


admin.site.unregister(User)


@admin.register(User)
class FrontPorchUserAdmin(UserAdmin):
    list_display = (*UserAdmin.list_display, "last_login")
    add_form = AccountCreationForm
    form = AccountChangeForm
    add_fieldsets = (
        (
            None,
            {
                "fields": (
                    "username",
                    "email",
                    "usable_password",
                    "password1",
                    "password2",
                )
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change or "email" in form.changed_data:
            sync_account_email(obj)


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ("name", "timezone", "created_at", "updated_at")
    search_fields = ("name", "notes")
    ordering = ("name",)

    def get_deleted_objects(self, objs, request):
        deleted_objects, model_count, perms_needed, protected = (
            super().get_deleted_objects(objs, request)
        )
        # Activity stays read-only on its own, but belongs to the family's
        # deletion cascade. Keep every other permission and protection check.
        perms_needed.discard(FamilyActivity._meta.verbose_name)
        return deleted_objects, model_count, perms_needed, protected


@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "family",
        "email",
        "dial_extension",
        "call_destination",
        "is_guardian",
    )
    list_filter = ("family", "is_guardian")
    search_fields = ("display_name", "user__email", "phone", "family__name")
    readonly_fields = ("email",)
    autocomplete_fields = ("user",)
    list_select_related = ("family", "user")
    ordering = ("family__name", "display_name")

    def get_readonly_fields(self, request, obj=None):
        return ("email", "dial_extension") if obj else ("email",)


@admin.register(Child)
class ChildAdmin(admin.ModelAdmin):
    fields = ("family", "name", "spoken_name", "notes")
    list_display = ("name", "spoken_name", "family", "created_at")
    list_filter = ("family",)
    search_fields = ("name", "spoken_name", "family__name", "notes")
    ordering = ("family__name", "name")


@admin.register(ChildBlackoutPeriod)
class ChildBlackoutPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "child",
        "day_group",
        "start_time",
        "end_time",
        "approved_by",
        "is_active",
    )
    list_filter = ("is_active", "day_group", "child__family")
    search_fields = (
        "label",
        "child__name",
        "child__family__name",
        "approved_by__display_name",
        "notes",
    )
    ordering = ("child__family__name", "child__name", "day_group", "start_time")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        "friendly_name",
        "owner_display_name",
        "owner_type",
        "sip_extension",
        "sip_username",
        "is_active",
        "wireguard_peer",
    )
    list_filter = (
        "is_active",
        "assigned_child__family",
        "assigned_parent__family",
        "assigned_family",
    )
    search_fields = (
        "friendly_name",
        "sip_extension",
        "sip_username",
        "assigned_child__name",
        "assigned_child__family__name",
        "assigned_parent__display_name",
        "assigned_parent__family__name",
        "assigned_family__name",
    )
    ordering = ("sip_extension", "friendly_name")


class WireGuardPeerForm(forms.ModelForm):
    public_key = forms.CharField(required=False, max_length=44,
                                 help_text="Paste an existing client's public key, or leave blank to generate a new downloadable connection.")
    class Meta:
        model = WireGuardPeer
        fields = "__all__"

    def clean(self):
        data = super().clean()
        if self.instance._state.adding and not data.get("public_key"):
            from django.core.exceptions import ImproperlyConfigured, ValidationError
            from .wireguard import generate_peer_keys
            try:
                generate_peer_keys(self.instance)
                data["public_key"] = self.instance.public_key
            except ImproperlyConfigured:
                raise ValidationError("The operator must configure private peer-key storage before creating a new connection.") from None
        if self.instance._state.adding and not data.get("client_address"):
            # Django admin keeps this POST in a transaction through save_model.
            from .models import lock_extension_namespace
            lock_extension_namespace()
            data["client_address"] = WireGuardPeer.available_address()
        return data


@admin.register(WireGuardPeer)
class WireGuardPeerAdmin(admin.ModelAdmin):
    form = WireGuardPeerForm
    list_display = ("name", "family", "provisioning_method", "client_address", "is_active",
                    "last_applied_at", "last_handshake_at")
    list_filter = ("family", "provisioning_method", "is_active")
    search_fields = ("name", "family__name")
    exclude = ("encrypted_secrets",)
    readonly_fields = ("last_applied_at", "last_handshake_at")
    actions = ("disable_peers", "download_configuration")

    def get_readonly_fields(self, request, obj=None):
        return (*self.readonly_fields, "public_key", "client_address") if obj else self.readonly_fields

    def save_model(self, request, obj, form, change):
        from .wireguard import audit
        old_family_id = WireGuardPeer.objects.filter(pk=obj.pk).values_list("family_id", flat=True).first() if change else None
        super().save_model(request, obj, form, change)
        audit(obj, request.user, f"{'Updated' if change else 'Added'} network connection: {obj.name}.")
        if old_family_id and old_family_id != obj.family_id:
            FamilyActivity.objects.create(family_id=old_family_id, actor=request.user,
                                          description="A network connection was transferred out of this family.",
                                          details={"wireguard_peer_id": str(obj.pk)})

    @admin.action(description="Disable selected network connections", permissions=["change"])
    def disable_peers(self, request, queryset):
        from django.db import transaction
        from .models import lock_extension_namespace
        from .wireguard import audit
        with transaction.atomic():
            lock_extension_namespace()
            for peer in queryset.filter(is_active=True):
                peer.is_active = False
                peer.save(update_fields=["is_active", "updated_at"])
                audit(peer, request.user, f"Disabled network connection: {peer.name}.")

    def delete_model(self, request, obj):
        from django.db import transaction
        from .models import lock_extension_namespace
        from .wireguard import audit
        with transaction.atomic():
            lock_extension_namespace()
            audit(obj, request.user, f"Removed network connection: {obj.name}.")
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        from django.db import transaction
        from .models import lock_extension_namespace
        from .wireguard import audit
        with transaction.atomic():
            lock_extension_namespace()
            for peer in queryset:
                audit(peer, request.user, f"Removed network connection: {peer.name}.")
            super().delete_queryset(request, queryset)

    @admin.action(description="Download selected client configuration (one connection)", permissions=["change"])
    @sensitive_variables()
    def download_configuration(self, request, queryset):
        from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
        from django.http import HttpResponse
        from .wireguard import audit, client_configuration
        from frontporch.vpn_config import VPNConfigurationError
        peers = list(queryset[:2])
        if len(peers) != 1:
            self.message_user(request, "Select one connection to download.", level="error")
            return
        peer = peers[0]
        if not self.has_change_permission(request, peer):
            raise PermissionDenied
        try:
            content = client_configuration(peer)
        except (ValidationError, ImproperlyConfigured, VPNConfigurationError):
            self.message_user(request, "Configuration unavailable. Imported clients keep their original file; new connections need complete server settings.", level="error")
            return
        audit(peer, request.user, f"Downloaded client configuration for network connection: {peer.name}.")
        response = HttpResponse(content, content_type="application/octet-stream")
        response["Content-Disposition"] = 'attachment; filename="frontporch.conf"'
        response["Cache-Control"] = "no-store, private, max-age=0"
        response["Pragma"] = "no-cache"
        response["X-Content-Type-Options"] = "nosniff"
        return response


@admin.register(ExternalPhoneNumber)
class ExternalPhoneNumberAdmin(admin.ModelAdmin):
    list_display = ("normalized_number", "created_at")
    search_fields = ("normalized_number",)
    ordering = ("normalized_number",)


@admin.register(ExternalNumberExtension)
class ExternalNumberExtensionAdmin(admin.ModelAdmin):
    list_display = (
        "dial_extension",
        "external_phone_number",
        "family_contact_labels",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = (
        "dial_extension",
        "external_phone_number__normalized_number",
        "external_phone_number__family_contacts__label",
        "external_phone_number__family_contacts__family__name",
        "notes",
    )
    ordering = ("dial_extension",)

    @admin.display(description="Family contacts")
    def family_contact_labels(self, obj):
        labels = [
            f"{contact.label} ({contact.family})"
            for contact in obj.external_phone_number.family_contacts.select_related(
                "family"
            ).order_by("family__name", "label")[:5]
        ]
        return ", ".join(labels)


@admin.register(ChildLandline)
class ChildLandlineAdmin(admin.ModelAdmin):
    list_display = (
        "child",
        "external_phone_number",
        "dial_extension",
        "approved_by",
        "is_active",
    )
    list_filter = ("is_active", "child__family")
    search_fields = (
        "child__name",
        "child__family__name",
        "external_phone_number__normalized_number",
        "dial_extension",
        "approved_by__display_name",
        "notes",
    )
    ordering = ("child__family__name", "child__name", "dial_extension")


@admin.register(PublicPhoneNumber)
class PublicPhoneNumberAdmin(admin.ModelAdmin):
    list_display = (
        "normalized_number",
        "label",
        "assigned_family",
        "provider_name",
        "is_active",
    )
    list_filter = ("is_active", "assigned_family", "provider_name")
    search_fields = (
        "normalized_number",
        "label",
        "assigned_family__name",
        "provider_name",
        "notes",
    )
    ordering = ("normalized_number",)


@admin.register(FamilyContact)
class FamilyContactAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "family",
        "external_phone_number",
        "dial_extension_display",
    )
    list_filter = ("family",)
    search_fields = (
        "label",
        "family__name",
        "external_phone_number__normalized_number",
        "external_phone_number__dialable_extension__dial_extension",
    )
    ordering = ("family__name", "label")

    @admin.display(description="Dial extension")
    def dial_extension_display(self, obj):
        extension = obj.dial_extension
        if not extension:
            return ""
        return extension.dial_extension


@admin.register(ExternalContactPermission)
class ExternalContactPermissionAdmin(admin.ModelAdmin):
    list_display = (
        "external_phone_number",
        "child",
        "approved_by",
        "is_active",
        "created_at",
    )
    list_filter = ("child__family",)
    search_fields = (
        "external_phone_number__normalized_number",
        "child__name",
        "child__family__name",
        "approved_by__display_name",
    )
    ordering = ("child__family__name", "child__name", "external_phone_number")


@admin.register(DialShortcut)
class DialShortcutAdmin(admin.ModelAdmin):
    list_display = (
        "source_device",
        "digits",
        "target_display",
        "label",
        "approved_by",
        "is_active",
    )
    list_filter = (
        "is_active",
        "source_device__assigned_child__family",
        "source_device__assigned_parent__family",
        "source_device__assigned_family",
    )
    search_fields = (
        "digits",
        "label",
        "source_device__friendly_name",
        "source_device__sip_extension",
        "internal_target_device__friendly_name",
        "internal_target_device__sip_extension",
        "external_target_extension__dial_extension",
        "external_target_extension__external_phone_number__normalized_number",
        "parent_target__display_name",
        "parent_target__phone",
        "child_landline_target__child__name",
        "child_landline_target__child__family__name",
        "child_landline_target__dial_extension",
        "child_landline_target__external_phone_number__normalized_number",
        "conference_group_target__name",
        "conference_group_target__dial_extension",
        "approved_by__display_name",
        "notes",
    )
    ordering = ("source_device__friendly_name", "digits")

    @admin.display(description="Target")
    def target_display(self, obj):
        return (
            obj.internal_target_device
            or obj.external_target_extension
            or obj.parent_target
            or obj.child_landline_target
            or obj.conference_group_target
        )


@admin.register(ChildLandlineDialShortcut)
class ChildLandlineDialShortcutAdmin(admin.ModelAdmin):
    list_display = (
        "source_landline",
        "digits",
        "target_child",
        "label",
        "approved_by",
        "is_active",
    )
    list_filter = (
        "is_active",
        "source_landline__child__family",
        "target_child__family",
    )
    search_fields = (
        "digits",
        "label",
        "source_landline__child__name",
        "source_landline__child__family__name",
        "source_landline__dial_extension",
        "source_landline__external_phone_number__normalized_number",
        "target_child__name",
        "target_child__family__name",
        "target_child__devices__sip_extension",
        "target_child__landlines__dial_extension",
        "approved_by__display_name",
        "notes",
    )
    ordering = (
        "source_landline__child__family__name",
        "source_landline__child__name",
        "digits",
    )


@admin.register(ConferenceGroup)
class ConferenceGroupAdmin(admin.ModelAdmin):
    class ConferenceGroupAdminForm(forms.ModelForm):
        class Meta:
            model = ConferenceGroup
            fields = "__all__"

        def _save_m2m(self):
            # Keep household approval continuous when staff swaps siblings.
            selected = set(self.cleaned_data["members"].values_list("pk", flat=True))
            current = set(self.instance.members.values_list("pk", flat=True))
            self.instance.members.add(*(selected - current))
            self.instance.members.remove(*(current - selected))

        def clean_members(self):
            members = self.cleaned_data["members"]
            if self.cleaned_data.get("calling_enabled") and members.count() < 2:
                raise forms.ValidationError(
                    "Choose at least two children before enabling calling."
                )
            return members

        def clean(self):
            cleaned_data = super().clean()
            if cleaned_data.get("calling_enabled") and not cleaned_data.get(
                "is_active"
            ):
                self.add_error(
                    "calling_enabled",
                    "Calling cannot be enabled for an inactive conference group.",
                )
            return cleaned_data

    form = ConferenceGroupAdminForm
    list_display = (
        "name",
        "dial_extension",
        "calling_enabled",
        "ring_timeout_seconds",
        "approved_by",
        "is_active",
        "member_count",
        "created_at",
    )
    list_filter = ("calling_enabled", "is_active")
    search_fields = (
        "name",
        "dial_extension",
        "members__name",
        "members__family__name",
        "approved_by__display_name",
    )
    filter_horizontal = ("members",)
    ordering = ("dial_extension", "name")

    @admin.display(description="Members")
    def member_count(self, obj):
        return obj.members.count()


@admin.register(ChildConnection)
class ChildConnectionAdmin(admin.ModelAdmin):
    list_display = ("child_a", "child_b", "is_active", "approved_by_a", "approved_by_b")
    list_filter = ("is_active",)
    search_fields = ("child_a__name", "child_b__name")


@admin.register(
    ConnectionInvitation, GroupInvitation, GuardianInvitation, FamilyInvitation, FamilyActivity
)
class PortalHistoryAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return ("details",) if self.model is FamilyActivity else ()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_exclude(self, request, obj=None):
        return (
            ("token_digest",)
            if self.model in {GuardianInvitation, FamilyInvitation}
            else ()
        )
