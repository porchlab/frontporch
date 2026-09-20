import secrets

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations, models
import django.db.models.deletion


def provision_accounts(apps, schema_editor):
    db = schema_editor.connection.alias
    User = apps.get_model(settings.AUTH_USER_MODEL)
    Parent = apps.get_model("directory", "Parent")
    EmailAddress = apps.get_model("account", "EmailAddress")
    users = {user.pk: user for user in User.objects.using(db).all()}
    parents = list(Parent.objects.using(db).order_by("pk"))
    emails = {pk: user.email.strip().lower() for pk, user in users.items()}

    # Resolve all identities before creating anything. Never merge families or
    # grant access to an existing account based only on matching legacy email.
    for parent in parents:
        old_email = parent.email.strip().lower()
        if parent.user_id:
            account_email = emails[parent.user_id]
            if old_email and account_email and old_email != account_email:
                raise RuntimeError(
                    f"Parent {parent.pk} and User {parent.user_id} have different emails. "
                    "Reconcile them in private admin before retrying the migration."
                )
            emails[parent.user_id] = account_email or old_email
        else:
            emails[f"parent-{parent.pk}"] = old_email

    owners = {}
    for owner, email in emails.items():
        if not email:
            continue
        if email in owners:
            raise RuntimeError(
                f"Duplicate account email for identities {owners[email]} and {owner}. "
                "Resolve duplicate emails or link the intended user in private admin "
                "before retrying the migration."
            )
        owners[email] = owner

    for parent in parents:
        if parent.user_id:
            continue
        username = f"guardian_{secrets.token_hex(12)}"
        while User.objects.using(db).filter(username__iexact=username).exists():
            username = f"guardian_{secrets.token_hex(12)}"
        user = User.objects.using(db).create(
            username=username,
            email=emails[f"parent-{parent.pk}"],
            password=make_password(secrets.token_urlsafe(48)),
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        Parent.objects.using(db).filter(pk=parent.pk).update(user_id=user.pk)
        users[user.pk] = user
        emails[user.pk] = user.email

    for pk, user in users.items():
        email = emails[pk]
        if user.email != email:
            User.objects.using(db).filter(pk=pk).update(email=email)
        if email:
            EmailAddress.objects.using(db).get_or_create(
                user_id=pk,
                email=email,
                defaults={"primary": True, "verified": False},
            )


def restore_contact_emails(apps, schema_editor):
    db = schema_editor.connection.alias
    Parent = apps.get_model("directory", "Parent")
    for parent in Parent.objects.using(db).select_related("user"):
        if parent.user_id:
            Parent.objects.using(db).filter(pk=parent.pk).update(
                email=parent.user.email
            )
    # Keep users, passwords and links: rolling back must not destroy credentials.


class Migration(migrations.Migration):
    dependencies = [
        ("directory", "0019_family_invitations"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("account", "0009_emailaddress_unique_primary_email"),
    ]

    operations = [
        migrations.RunPython(provision_accounts, restore_contact_emails),
        migrations.AlterField(
            model_name="parent",
            name="user",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="frontporch_parent",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RemoveField(model_name="parent", name="email"),
    ]
