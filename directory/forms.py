from django import forms
from django.contrib.auth.forms import UserCreationForm
from allauth.account.forms import LoginForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import render

from .accounts import validate_account_email
from .registration import (
    create_invited_family,
    lock_registration_invitation,
    social_signup_invitation,
)
from .models import (
    Child,
    ChildBlackoutPeriod,
    ConferenceGroup,
    ExternalContactPermission,
    ExternalPhoneNumber,
    Family,
    FamilyContact,
    Parent,
)


class FamilyRegistrationFields(forms.Form):
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


class ParentRegistrationForm(FamilyRegistrationFields, UserCreationForm):
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

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            invitation = lock_registration_invitation(self.invitation, user.email)
            user.save()
            create_invited_family(user, invitation, self.cleaned_data)
        return user


class InvitedSocialSignupForm(FamilyRegistrationFields, SocialSignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.invitation = social_signup_invitation(self.sociallogin)
        self.fields.pop("username", None)
        self.fields["email"].disabled = True
        if self.invitation:
            self.initial["email"] = self.invitation.email
        self.fields["email"].help_text = "Verified with Google. No password is needed."

    def clean_email(self):
        return validate_account_email(self.cleaned_data["email"])

    def try_save(self, request):
        # allauth clears its pending signup before saving. Restore it if a
        # concurrent invitation/email change prevents this submission.
        pending = self.sociallogin.serialize()
        try:
            return super().try_save(request)
        except ValidationError as error:
            request.session["socialaccount_sociallogin"] = pending
            self.add_error(None, error)
            return None, render(request, "socialaccount/signup.html", {"form": self})


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
        ].help_text = f"Times use {settings.TIME_ZONE}, the phone system’s time zone. An end time before the start time means the next morning. The day group selects the days quiet hours start."

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


def _lock_group_children(members, family):
    # ModelMultipleChoiceField initially validates ownership without row locks.
    # Recheck the selected identities under locks held through the membership write.
    selected = {child.pk for child in members}
    locked = Child.objects.select_for_update().filter(pk__in=selected).order_by("pk")
    children = list(locked)
    if len(children) != len(selected) or any(
        child.family_id != family.pk for child in children
    ):
        raise forms.ValidationError(
            "A selected child no longer belongs to your family. Reload the form and try again."
        )
    return locked


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
        self.family = family
        self.fields["members"].queryset = Child.objects.filter(family=family)
        self.fields["members"].label = "Your children in this group"
        self.shared = bool(
            self.instance.pk
            and self.instance.members.exclude(family=family).exists()
        )
        if self.instance.pk:
            self.fields["members"].required = False
            self.initial["members"] = list(
                self.instance.members.filter(family=family).values_list("pk", flat=True)
            )
            self.fields["members"].help_text = (
                "Uncheck a child to leave the group. Uncheck all to leave as a family."
            )
        if self.shared:
            for field in ("name", "is_active", "notes"):
                del self.fields[field]

    def clean_members(self):
        members = self.cleaned_data["members"]
        if not self.instance.pk and not members:
            raise forms.ValidationError("Choose at least one child.")
        return _lock_group_children(members, self.family)

    def _save_m2m(self):
        # Replace only this household's approvals; other households control theirs.
        selected = set(self.cleaned_data["members"].values_list("pk", flat=True))
        current = set(
            self.instance.members.filter(family=self.family).values_list("pk", flat=True)
        )
        # A replacement within the household is not a departure: add first so
        # membership-removal handlers see the retained household approval.
        self.instance.members.add(*(selected - current))
        self.instance.members.remove(*(current - selected))


class GroupInvitationForm(forms.Form):
    family = forms.ModelChoiceField(
        queryset=Family.objects.none(), required=False, label="Listed family"
    )
    code = forms.CharField(
        max_length=32, required=False, label="Or enter a family invite code"
    )

    def __init__(self, *args, family, **kwargs):
        super().__init__(*args, **kwargs)
        self.family = family
        self.fields["family"].queryset = Family.objects.filter(
            directory_listed=True
        ).exclude(pk=family.pk)

    def clean(self):
        data = super().clean()
        target, code = data.get("family"), data.get("code")
        if bool(target) == bool(code):
            raise forms.ValidationError("Choose a listed family or enter a family code.")
        if code:
            target = Family.objects.filter(invite_code=code).exclude(pk=self.family.pk).first()
            if target is None:
                raise forms.ValidationError("This code is not available. Ask the parent for their current family code.")
        # Directory visibility and private codes can be revoked during initial
        # field validation. Hold a lock through invitation creation and recheck.
        target = Family.objects.select_for_update(no_key=True).filter(pk=target.pk).first()
        if target is None or (
            target.invite_code != code if code else not target.directory_listed
        ):
            raise forms.ValidationError(
                "This invitation option is no longer available. Ask the parent for their current family code."
            )
        data["target_family"] = target
        return data


class GroupAcceptForm(forms.Form):
    members = forms.ModelMultipleChoiceField(
        queryset=Child.objects.none(), widget=forms.CheckboxSelectMultiple,
        label="Your children to join the group",
    )

    def __init__(self, *args, family, **kwargs):
        super().__init__(*args, **kwargs)
        self.family = family
        self.fields["members"].queryset = Child.objects.filter(family=family)

    def clean_members(self):
        return _lock_group_children(self.cleaned_data["members"], self.family)


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
        fields = ("display_name", "phone", "call_destination", "directory_visible")
        labels = {
            "display_name": "Your name",
            "phone": "Your phone number",
            "call_destination": "Where calls to you ring",
            "directory_visible": "Show my name when our family is listed",
        }
        help_texts = {
            "phone": "Used when you choose to ring your phone number. It never appears in the directory.",
            "call_destination": "Your children use the same extension and shortcuts for every choice.",
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
        from .services import shortcut_destinations, shortcut_targets

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
                    if shortcut_targets(instance, field, obj.pk)
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
            "parent_target",
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
        self.fields["login"].widget.attrs.pop("autofocus", None)
        self.fields["login"].widget.attrs["autocomplete"] = "username"
