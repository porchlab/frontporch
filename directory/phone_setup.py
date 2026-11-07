"""Family-facing enrollment. No provider calls or secret generation in HTTP requests."""

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.decorators.debug import sensitive_post_parameters

from .gdms import normalize_mac
from .models import Child, Parent, PhoneEnrollment, PhoneEnrollmentState as State
from .services import record_activity
from .views import _require_parent


class RegistrationForm(forms.Form):
    person = forms.ChoiceField(label="Who is this phone for?")
    friendly_name = forms.CharField(label="Phone name", max_length=80, initial="FrontPorch phone")
    mac = forms.CharField(label="MAC address", max_length=17, help_text="The 12 letters and numbers beside MAC on the box label.", widget=forms.TextInput(attrs={"autocapitalize": "characters", "autocomplete": "off", "spellcheck": "false"}))
    serial = forms.RegexField(label="Serial number (S/N)", regex=r"^[A-Za-z0-9]{8,64}$", max_length=64, help_text="Use S/N, not the Wi-Fi password or part number.", widget=forms.TextInput(attrs={"autocapitalize": "characters", "autocomplete": "off", "spellcheck": "false"}))
    possession = forms.BooleanField(label="I have this WP816 phone and have checked the label details.")

    def __init__(self, *args, family, **kwargs):
        super().__init__(*args, **kwargs)
        self.people = {f"child:{c.pk}": c for c in Child.objects.filter(family=family)}
        self.people.update({f"parent:{p.pk}": p for p in Parent.objects.filter(family=family, user__is_active=True)})
        self.fields["person"].choices = [("", "Choose a person"), *[
            (key, obj.name if isinstance(obj, Child) else obj.display_name)
            for key, obj in self.people.items()
        ], ("family", "Shared household phone")]

    def clean_mac(self):
        try:
            return normalize_mac(self.cleaned_data["mac"])
        except ValueError as error:
            raise forms.ValidationError(str(error)) from None

    def clean_serial(self):
        return self.cleaned_data["serial"].upper()


def _enabled():
    if not settings.PHONE_ENROLLMENT_ENABLED:
        raise Http404


def _family_enrollment(request, enrollment_id):
    parent = _require_parent(request)
    return parent, get_object_or_404(PhoneEnrollment.objects.select_related(
        "assigned_child", "assigned_parent", "device__wireguard_peer"), pk=enrollment_id, family=parent.family)


@login_required
@require_GET
@never_cache
def index(request):
    _enabled()
    parent = _require_parent(request)
    return render(request, "directory/phone_setup_list.html", {
        "section": "phones", "enrollments": parent.family.phone_enrollments.select_related("assigned_child", "assigned_parent", "device"),
    })


@login_required
@require_http_methods(["GET", "POST"])
@never_cache
@sensitive_post_parameters("mac", "serial")
def register(request):
    _enabled()
    parent = _require_parent(request)
    initial = {}
    if request.GET.get("person"):
        initial["person"] = request.GET["person"]
    form = RegistrationForm(request.POST if request.method == "POST" else None, family=parent.family, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                # Serialize each family's cap and recheck access after a concurrent removal.
                actor = Parent.objects.select_for_update().get(pk=parent.pk, is_guardian=True, user__is_active=True)
                type(parent.family).objects.select_for_update().get(pk=parent.family_id)
                active = PhoneEnrollment.objects.filter(family=parent.family).exclude(state__in=[State.CANCELLED, State.READY])
                if active.count() >= 10:
                    raise ValidationError("Finish an existing phone setup before adding another.")
                duplicate = PhoneEnrollment.objects.filter(Q(mac=form.cleaned_data["mac"]) | Q(serial=form.cleaned_data["serial"]))
                if duplicate.exists():
                    # A repeated submission resumes the identical claim in this family only.
                    same = duplicate.filter(family=parent.family, mac=form.cleaned_data["mac"], serial=form.cleaned_data["serial"]).first()
                    if same:
                        return redirect("directory:phone_setup_detail", enrollment_id=same.pk)
                    raise ValidationError("This phone cannot be registered with those details. Check the label or contact FrontPorch for help.")
                selected = form.people.get(form.cleaned_data["person"])
                if selected is not None:
                    selected = type(selected).objects.select_for_update().get(pk=selected.pk, family=parent.family)
                enrollment = PhoneEnrollment(
                    family=parent.family, requested_by=actor,
                    assigned_child=selected if isinstance(selected, Child) else None,
                    assigned_parent=selected if isinstance(selected, Parent) else None,
                    friendly_name=form.cleaned_data["friendly_name"],
                    mac=form.cleaned_data["mac"], serial=form.cleaned_data["serial"],
                )
                enrollment.full_clean()
                enrollment.save()
                record_activity(parent, f"Started phone setup for {enrollment.person_name}: {enrollment.friendly_name}.")
        except (IntegrityError, ValidationError, Parent.DoesNotExist, Child.DoesNotExist):
            form.add_error(None, "We couldn't register this phone. Check the label details and your family access, or contact FrontPorch for help.")
        else:
            return redirect("directory:phone_setup_detail", enrollment_id=enrollment.pk)
    return render(request, "directory/phone_setup_register.html", {"section": "phones", "form": form})


PROBLEMS = {
    "identity": "We couldn't verify this phone. Check the MAC and S/N on its box and contact FrontPorch for help.",
    "ownership": "This phone needs an ownership check before setup can continue. Contact FrontPorch for help.",
    "model": "Automatic setup supports the Grandstream WP816. This phone needs a model check.",
    "firmware": "This phone has a software version that needs a compatibility check. Contact FrontPorch for help.",
    "upgrade_timeout": "The update has not finished yet. Keep the phone on its charger and connected to Wi-Fi. Use Check again after it finishes.",
    "delivery_timeout": "The phone hasn't finished receiving its settings. Keep it connected to Wi-Fi and contact FrontPorch for help.",
    "access": "Family access changed during setup. Another guardian can contact FrontPorch to continue.",
    "service": "FrontPorch is having trouble completing setup. Your progress is saved; please contact FrontPorch for help.",
}


def public_progress(enrollment):
    return {
        "state": enrollment.state,
        "title": enrollment.get_state_display(),
        "message": PROBLEMS.get(enrollment.problem, ""),
        "firmware": enrollment.firmware_version,
        "extension": enrollment.device.sip_extension if enrollment.device_id else "",
        "finished": enrollment.state in (State.READY, State.CANCELLED, State.HELP),
        "downloaded": bool(enrollment.profile_downloaded_at),
    }


@login_required
@require_GET
@never_cache
def detail(request, enrollment_id):
    _enabled()
    _, enrollment = _family_enrollment(request, enrollment_id)
    return render(request, "directory/phone_setup_detail.html", {
        "section": "phones", "enrollment": enrollment, "progress": public_progress(enrollment),
    })


@login_required
@require_GET
@never_cache
def progress(request, enrollment_id):
    _enabled()
    _, enrollment = _family_enrollment(request, enrollment_id)
    return JsonResponse(public_progress(enrollment))


@login_required
@require_POST
@never_cache
def check_again(request, enrollment_id):
    _enabled()
    parent, enrollment = _family_enrollment(request, enrollment_id)
    # This only schedules fresh reads. It must never repeat an uncertain write.
    if enrollment.state not in (State.READY, State.CANCELLED):
        changes = {"next_attempt_at": timezone.now()}
        if enrollment.problem == "upgrade_timeout":
            changes.update(state=State.UPGRADING, problem="")
        PhoneEnrollment.objects.filter(pk=enrollment.pk).update(**changes)
        record_activity(parent, f"Requested another setup check: {enrollment.friendly_name}.")
        messages.success(request, "We'll check the phone again. Keep it on its charger and connected to Wi-Fi.")
    return redirect("directory:phone_setup_detail", enrollment_id=enrollment.pk)
