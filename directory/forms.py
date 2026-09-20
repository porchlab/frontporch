from django import forms
from django.contrib.auth.forms import UserCreationForm
from allauth.account.forms import LoginForm
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction

from .accounts import sync_account_email, validate_account_email
from .models import (
    Child,
    ChildBlackoutPeriod,
    ConferenceGroup,
    ExternalContactPermission,
    ExternalPhoneNumber,
    Family,
    FamilyInvitation,
    FamilyContact,
    Parent,
)


class ParentRegistrationForm(UserCreationForm):
    username = forms.CharField(required=False, widget=forms.HiddenInput, max_length=150)

    def __init__(self, *args, invitation, **kwargs):
        self.invitation = invitation
        super().__init__(*args, **kwargs)
        self.fields["email"].initial = invitation.email
        self.fields["email"].disabled = True
        self.fields["email"].help_text = "This invitation is for this email address."

    def clean_username(self):
        import secrets

        username = self.cleaned_data.get("username") or "guardian_" + secrets.token_hex(
            12
        )
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already in use.")
        return username

    family_name = forms.CharField(max_length=200)
    display_name = forms.CharField(
        max_length=200,
        label="Guardian name",
        help_text="Your name as the parent or guardian managing this account.",
    )
    email = forms.EmailField()
    directory_listed = forms.BooleanField(
        required=False,
        label="List my family in the private parent directory",
        help_text="Only your family name and your guardian name are shown. You can hide your listing at any time.",
    )
    phone = forms.CharField(max_length=32, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account already uses this email. Log in with that account."
            )
        return validate_account_email(email)

    def clean_family_name(self):
        family_name = self.cleaned_data["family_name"]
        if Family.objects.filter(name__iexact=family_name).exists():
            raise forms.ValidationError("A family with this name already exists.")
        return family_name

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        if not phone:
            return phone
        try:
            return ExternalPhoneNumber.normalize(phone)
        except ValidationError as exc:
            raise forms.ValidationError("Enter a valid phone number.") from exc

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            from .services import lock_email_identity, record_activity

            # Recheck under locks: two submissions must never reuse one invitation.
            Family.objects.select_for_update().get(pk=self.invitation.family_id)
            invitation = FamilyInvitation.objects.select_for_update().get(
                pk=self.invitation.pk
            )
            if not invitation.available or invitation.email != user.email:
                raise ValidationError(
                    "This invitation is no longer available. Ask an existing family for a new invitation."
                )
            lock_email_identity(user.email)
            validate_account_email(user.email)
            user.save()
            family = Family.objects.create(
                name=self.cleaned_data["family_name"],
                directory_listed=self.cleaned_data["directory_listed"],
            )
            parent = Parent.objects.create(
                user=user,
                family=family,
                display_name=self.cleaned_data["display_name"],
                phone=self.cleaned_data["phone"],
                is_guardian=True,
                is_primary=True,
                directory_visible=self.cleaned_data["directory_listed"],
            )
            sync_account_email(user, verified=True)
            invitation.status = "accepted"
            invitation.accepted_family = family
            invitation.save(update_fields=["status", "accepted_family", "updated_at"])
            record_activity(parent, "Your family account is ready.")
            record_activity(
                invitation.invited_by,
                f"The {family.name} family accepted your invitation to FrontPorch.",
            )
        return user


class FamilyInvitationForm(forms.Form):
    email = forms.EmailField(label="Parent or guardian’s email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "This email already has an account. Invite a parent from a new family."
            )
        return validate_account_email(email)


class ChildForm(forms.ModelForm):
    def __init__(self, *args, family, **kwargs):
        super().__init__(*args, **kwargs)
        self.family = family
        self.fields["color"].required = False

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if (
            Child.objects.filter(family=self.family, name__iexact=name)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(
                "A child with this name already belongs to your family."
            )
        return name

    def clean_color(self):
        return self.cleaned_data.get("color") or self.instance.color or "yellow"

    class Meta:
        model = Child
        fields = ("name", "color", "notes")
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def _post_clean(self):
        self.instance.family = self.family
        super()._post_clean()


class ChildBlackoutPeriodForm(forms.ModelForm):
    def __init__(self, *args, child, approved_by, **kwargs):
        super().__init__(*args, **kwargs)
        self.child = child
        self.approved_by = approved_by
        from django.conf import settings

        self.fields[
            "start_time"
        ].help_text = f"Times use {settings.TIME_ZONE}, the phone system’s time zone. End time must be later on the same day."

    class Meta:
        model = ChildBlackoutPeriod
        fields = ("label", "day_group", "start_time", "end_time", "is_active", "notes")
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def _post_clean(self):
        self.instance.child = self.child
        self.instance.approved_by = self.approved_by
        super()._post_clean()


class FamilyContactForm(forms.Form):
    label = forms.CharField(max_length=200, label="Contact name")
    phone_number = forms.CharField(max_length=32)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, family=None, instance=None, **kwargs):
        self.family, self.instance = family, instance
        if instance:
            kwargs.setdefault(
                "initial",
                {
                    "label": instance.label,
                    "phone_number": instance.external_phone_number.normalized_number,
                    "notes": instance.notes,
                },
            )
        super().__init__(*args, **kwargs)

    def clean_phone_number(self):
        try:
            number = ExternalPhoneNumber.normalize(self.cleaned_data["phone_number"])
        except ValidationError as exc:
            raise forms.ValidationError("Enter a valid phone number.") from exc
        existing = FamilyContact.objects.filter(
            family=self.family, external_phone_number__normalized_number=number
        )
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError(
                "This number is already saved in your family contacts."
            )
        return number

    def save(self, family):
        number, _ = ExternalPhoneNumber.objects.get_or_create_normalized(
            self.cleaned_data["phone_number"]
        )
        contact = self.instance or FamilyContact(family=family)
        contact.external_phone_number = number
        contact.label = self.cleaned_data["label"]
        contact.notes = self.cleaned_data["notes"]
        contact.save()
        return contact


class ExternalContactPermissionForm(forms.ModelForm):
    class Meta:
        model = ExternalContactPermission
        fields = ("child", "external_phone_number", "notes")
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, family, **kwargs):
        super().__init__(*args, **kwargs)
        self.family = family
        self.fields["child"].queryset = Child.objects.filter(family=family)
        self.fields[
            "external_phone_number"
        ].queryset = ExternalPhoneNumber.objects.filter(
            family_contacts__family=family
        ).distinct()
        self.fields["external_phone_number"].label = "Family contact number"


class ConferenceGroupForm(forms.ModelForm):
    class Meta:
        model = ConferenceGroup
        fields = ("name", "members", "is_active", "notes")
        widgets = {
            "members": forms.CheckboxSelectMultiple,
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, family, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["members"].queryset = Child.objects.filter(family=family)

    def clean_members(self):
        members = self.cleaned_data["members"]
        if members.count() < 2:
            raise forms.ValidationError("Choose at least two children.")
        return members


class FamilySettingsForm(forms.ModelForm):
    class Meta:
        model = Family
        fields = ("name", "directory_listed")
        labels = {
            "name": "Family name",
            "directory_listed": "List our family in the private directory",
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if (
            Family.objects.filter(name__iexact=name)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError("A family with this name already exists.")
        return name


class GuardianProfileForm(forms.ModelForm):
    def clean_display_name(self):
        name = self.cleaned_data["display_name"].strip()
        if (
            Parent.objects.filter(
                family=self.instance.family, display_name__iexact=name
            )
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(
                "A guardian with this name already belongs to your family."
            )
        return name

    class Meta:
        model = Parent
        fields = ("display_name", "phone", "directory_visible")
        labels = {
            "display_name": "Your name",
            "phone": "Your phone number",
            "directory_visible": "Show my name when our family is listed",
        }
        help_texts = {
            "phone": "Your children can call this number. It never appears in the directory."
        }


class ShortcutForm(forms.Form):
    digits = forms.ChoiceField(
        label="Shortcut key", choices=[(str(n), str(n)) for n in range(1, 10)]
    )
    target = forms.ChoiceField(label="Approved person or group")
    label = forms.CharField(
        max_length=200, required=False, label="Familiar name (optional)"
    )
    is_active = forms.BooleanField(
        required=False, initial=True, label="Enable this shortcut"
    )

    def __init__(self, *args, source, parent, instance=None, **kwargs):
        from .models import DialShortcut
        from .services import shortcut_destinations

        self.source, self.parent = source, parent
        self.instance = instance or DialShortcut(
            source_device=source, approved_by=parent
        )
        self.destinations = shortcut_destinations(source)
        if instance:
            selected = next(
                (
                    key
                    for key, (field, obj, label) in self.destinations.items()
                    if getattr(instance, field + "_id") == obj.pk
                ),
                "",
            )
            kwargs.setdefault(
                "initial",
                {
                    "digits": instance.digits,
                    "target": selected,
                    "label": instance.label,
                    "is_active": instance.is_active,
                },
            )
        super().__init__(*args, **kwargs)
        self.fields["target"].choices = [("", "Choose an approved destination")] + [
            (key, label) for key, (_, _, label) in self.destinations.items()
        ]

    def clean_digits(self):
        from .models import DialShortcut

        digits = self.cleaned_data["digits"]
        if (
            DialShortcut.objects.filter(source_device=self.source, digits=digits)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError("This key is already assigned on this phone.")
        return digits

    def save(self):
        shortcut = self.instance
        for field in (
            "internal_target_device",
            "external_target_extension",
            "parent_phone_target",
            "child_landline_target",
            "conference_group_target",
        ):
            setattr(shortcut, field, None)
        field, target, _ = self.destinations[self.cleaned_data["target"]]
        setattr(shortcut, field, target)
        shortcut.digits = self.cleaned_data["digits"]
        shortcut.label = self.cleaned_data["label"]
        shortcut.is_active = self.cleaned_data["is_active"]
        shortcut.approved_by = self.parent
        shortcut.save()
        return shortcut


class PhoneReservationForm(forms.Form):
    friendly_name = forms.CharField(max_length=200, label="Phone name")


class InviteCodeForm(forms.Form):
    code = forms.CharField(max_length=32, label="Family invite code", strip=True)


class ConnectionInvitationForm(forms.Form):
    children = forms.ModelMultipleChoiceField(
        queryset=Child.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Your children to include",
    )
    message = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="A little hello (optional)",
    )

    def __init__(self, *args, family, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["children"].queryset = Child.objects.filter(family=family)


class ConnectionAcceptForm(forms.Form):
    children = forms.ModelMultipleChoiceField(
        queryset=Child.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Your children to connect",
    )

    def __init__(self, *args, family, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["children"].queryset = Child.objects.filter(family=family)
        self.fields["children"].initial = list(
            self.fields["children"].queryset.values_list("pk", flat=True)
        )


class GuardianInvitationForm(forms.Form):
    display_name = forms.CharField(max_length=200, label="Guardian name")
    email = forms.EmailField(label="Guardian email")

    def __init__(self, *args, family, **kwargs):
        self.family = family
        super().__init__(*args, **kwargs)

    def clean_display_name(self):
        name = self.cleaned_data["display_name"].strip()
        if Parent.objects.filter(
            family=self.family, display_name__iexact=name, is_guardian=True
        ).exists():
            raise forms.ValidationError(
                "A guardian with this name already belongs to your family."
            )
        return name

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Parent.objects.filter(user__email__iexact=email, is_guardian=True).exists():
            raise forms.ValidationError(
                "This email already belongs to a family account."
            )
        if (
            EmailAddress.objects.filter(email__iexact=email)
            .exclude(user__email__iexact=email)
            .exists()
        ):
            raise forms.ValidationError("Use this guardian’s current account email.")
        return email


class GuardianJoinForm(UserCreationForm):
    username = forms.CharField(required=False, widget=forms.HiddenInput, max_length=150)

    def clean_username(self):
        import secrets

        username = self.cleaned_data.get("username") or "guardian_" + secrets.token_hex(
            12
        )
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already in use.")
        return username

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "password1", "password2")


class ParentAuthenticationForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].help_text = ""
        self.fields["login"].label = "Email or username"
        self.fields["login"].widget.attrs.update(
            {"autofocus": True, "autocomplete": "username"}
        )
