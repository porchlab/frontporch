from django.contrib import admin
from django import forms
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.contrib.auth.models import User

from .accounts import sync_account_email, validate_account_email

from .models import (
    AllowedChildFamilyRelationship,
    Child,
    ChildConnection,
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
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name", "notes")
    ordering = ("name",)


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


@admin.register(AllowedChildFamilyRelationship)
class AllowedChildFamilyRelationshipAdmin(admin.ModelAdmin):
    # Historical records only. Current calling permissions use ChildConnection.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    list_display = (
        "child",
        "target_family",
        "approved_by_child_family_guardian",
        "approved_by_target_family_guardian",
        "previously_approved",
        "created_at",
    )
    list_filter = ("child__family", "target_family")
    search_fields = (
        "child__name",
        "child__family__name",
        "target_family__name",
        "approved_by_child_family_guardian__display_name",
        "approved_by_target_family_guardian__display_name",
    )
    ordering = ("child__family__name", "child__name", "target_family__name")

    @admin.display(boolean=True, description="Historically approved (not a call grant)")
    def previously_approved(self, obj):
        return obj.is_active


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
    ConnectionInvitation, GuardianInvitation, FamilyInvitation, FamilyActivity
)
class PortalHistoryAdmin(admin.ModelAdmin):
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
