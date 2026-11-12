"""Recoverable phone removal, run under the enrollment worker's session lock."""

from django.db import transaction

from .enrollment_worker import operation, owned_inventory, revoke_profile, save
from .models import (
    Device, FamilyActivity, PhoneEnrollment, PhoneEnrollmentState as State,
    WireGuardPeer, lock_extension_namespace,
)


def needs_help(enrollment, problem):
    save(enrollment, state=State.DEREGISTER_HELP, problem=problem)
    FamilyActivity.objects.create(
        family=enrollment.family, description=f"Phone removal needs attention: {enrollment.friendly_name}.",
        details={"enrollment_id": str(enrollment.pk), "reason": problem},
    )


@transaction.atomic
def remove_local_phone(enrollment):
    """Remove credentials/shortcuts and the dedicated peer, preserving history."""
    lock_extension_namespace()
    locked = PhoneEnrollment.objects.select_for_update().get(pk=enrollment.pk)
    if locked.device_id:
        device = Device.objects.get(pk=locked.device_id)
        if device.owning_family.pk != locked.family_id:
            return False
        peer = device.wireguard_peer
        save(enrollment, device=None, encrypted_bootstrap="", profile_expires_at=None)
        device_id = device.pk
        device.delete()
        # A shared manually managed gateway must survive phone removal.
        if peer and peer.provisioning_method == WireGuardPeer.Provisioning.GDMS and not peer.devices.exists():
            peer.delete()
        FamilyActivity.objects.create(
            family=enrollment.family, description=f"Removed calling access: {enrollment.friendly_name}.",
            details={"enrollment_id": str(enrollment.pk), "device_id": device_id},
        )
    return True


@transaction.atomic
def finish(enrollment):
    save(enrollment, state=State.DEREGISTERED, problem="", encrypted_bootstrap="",
         profile_expires_at=None, profile_downloaded_at=None, consecutive_failures=0)
    FamilyActivity.objects.create(
        family=enrollment.family, description=f"Deregistered phone: {enrollment.friendly_name}.",
        details={"enrollment_id": str(enrollment.pk)},
    )


class DeregistrationWorker:
    def __init__(self, client, apply):
        self.client, self.apply = client, apply

    def task(self, enrollment, kind):
        prefix, expected_type = ("fp-reset-", 2) if kind == "reset" else ("fp-fw-", 3)
        row = self.client.task_by_name(org_id=enrollment.org_id, task_name=prefix + enrollment.pk.hex)
        if row and row["taskType"] != expected_type:
            needs_help(enrollment, "removal_ownership")
            return False
        return row

    def cancel_task(self, enrollment, kind):
        """Confirm removal of old tasks before permitting a new registration."""
        entry = enrollment.operations.filter(kind=kind).first()
        if not entry or entry.status == "rejected":
            return True
        row = self.task(enrollment, kind)
        if row is False:
            return False
        if row is None:
            if entry.status == "started":
                needs_help(enrollment, "removal_uncertain")
                return False
            return True
        if entry.reference and str(row["id"]) != entry.reference:
            needs_help(enrollment, "removal_ownership")
            return False
        if entry.status == "started":
            entry.status, entry.reference = "accepted", str(row["id"])
            entry.save(update_fields=["status", "reference", "updated_at"])
        cancellation = enrollment.operations.filter(kind="cancel_" + kind).first()
        if cancellation:
            # A lost response is reconciled by absence, never by repeating it.
            if cancellation.status != "accepted":
                needs_help(enrollment, "removal_uncertain")
            return False
        operation(enrollment, "cancel_" + kind, lambda: self.client.delete_task(row["id"]))
        # Recheck the inventory on a later worker pass, including accepted writes.
        return False

    def step(self, enrollment, now):
        revoke_profile(enrollment)
        if enrollment.state in (State.DEREGISTERED, State.DEREGISTER_HELP):
            return
        if not enrollment.removal_applied_at:
            save(enrollment, state=State.DEREGISTERING, problem="")
            if not remove_local_phone(enrollment):
                needs_help(enrollment, "removal_ownership")
                return
            # Retrying this local render/reload is safe after a process crash.
            self.apply(reload=True)
            save(enrollment, removal_applied_at=now, encrypted_bootstrap="")
            return

        add = enrollment.operations.filter(kind="add").first()
        if not enrollment.gdms_added_at and (not add or add.status == "rejected"):
            # No accepted/uncertain enrollment write: nothing in GDMS is ours.
            finish(enrollment)
            return
        if not enrollment.org_id:
            needs_help(enrollment, "removal_ownership")
            return
        row = self.client.device(enrollment.mac, enrollment.org_id)
        if row is not None and not owned_inventory(enrollment, row):
            needs_help(enrollment, "removal_ownership")
            return

        reset = enrollment.operations.filter(kind="reset").first()
        if not reset:
            if row is None:
                needs_help(enrollment, "removal_missing")
                return
            if not self.cancel_task(enrollment, "upgrade"):
                return
            reset = operation(enrollment, "reset", lambda: self.client.factory_reset(
                mac=enrollment.mac, org_id=enrollment.org_id,
                task_name="fp-reset-" + enrollment.pk.hex,
            ))
        if reset.status == "started":
            task = self.task(enrollment, "reset")
            if task is False:
                return
            if not task:
                needs_help(enrollment, "removal_uncertain")
                return
            reset.status, reset.reference = "accepted", str(task["id"])
            reset.save(update_fields=["status", "reference", "updated_at"])
        if reset.status != "accepted":
            needs_help(enrollment, "removal_rejected")
            return
        if not enrollment.reset_confirmed_at:
            save(enrollment, state=State.RESET_PENDING, problem="")
            return

        save(enrollment, state=State.REMOVING, problem="")
        if not self.cancel_task(enrollment, "reset"):
            return
        deletion = enrollment.operations.filter(kind="delete").first()
        if row is None:
            # Absence after a confirmed reset also reconciles a lost delete reply.
            finish(enrollment)
        elif deletion:
            if deletion.status != "accepted":
                needs_help(enrollment, "removal_uncertain")
        else:
            operation(enrollment, "delete", lambda: self.client.delete_device(
                mac=enrollment.mac, org_id=enrollment.org_id,
            ))
            # Keep the identity reserved until a subsequent inventory read is empty.
