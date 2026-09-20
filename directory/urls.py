from django.urls import path

from . import views, portal, guardians, family_invitations


app_name = "directory"

urlpatterns = [
    path("families/invite/", family_invitations.invite, name="family_invite"),
    path(
        "families/invitations/<int:invitation_id>/<str:action>/",
        family_invitations.invitation_action,
        name="family_invitation_action",
    ),
    path("phones/<int:device_id>/edit/", portal.phone_edit, name="phone_edit"),
    path("guardians/invite/", guardians.invite, name="guardian_invite"),
    path("guardians/join/<str:token>/", guardians.join, name="guardian_join"),
    path(
        "guardians/invitations/<int:invitation_id>/<str:action>/",
        guardians.invitation_action,
        name="guardian_invitation_action",
    ),
    path("guardians/<int:parent_id>/remove/", guardians.remove, name="guardian_remove"),
    path(
        "children/<int:child_id>/phones/new/", portal.phone_create, name="phone_create"
    ),
    path("families/code/", portal.invite_code, name="invite_code"),
    path("invitations/new/", portal.connection_invite, name="connection_invite"),
    path(
        "invitations/<int:invitation_id>/review/",
        portal.connection_review,
        name="connection_review",
    ),
    path(
        "invitations/<int:invitation_id>/<str:action>/",
        portal.invitation_action,
        name="invitation_action",
    ),
    path(
        "connections/<int:connection_id>/remove/",
        portal.connection_remove,
        name="connection_remove",
    ),
    path("welcome/", portal.welcome, name="welcome"),
    path("children/", portal.children, name="children"),
    path("children/<int:child_id>/", portal.child_detail, name="child_detail"),
    path("contacts/", portal.contacts, name="contacts"),
    path("contacts/<int:contact_id>/edit/", portal.contact_edit, name="contact_edit"),
    path("families/", portal.family_directory, name="family_directory"),
    path("connections/", portal.connections, name="connections"),
    path("invitations/", portal.invitations, name="invitations"),
    path("settings/", portal.family_settings, name="settings"),
    path("settings/<str:preference>/", portal.preference, name="preference"),
    path("phones/<int:device_id>/shortcuts/", portal.shortcuts, name="shortcuts"),
    path(
        "phones/<int:device_id>/shortcuts/new/",
        portal.shortcut_edit,
        name="shortcut_create",
    ),
    path(
        "phones/<int:device_id>/shortcuts/<int:shortcut_id>/",
        portal.shortcut_edit,
        name="shortcut_edit",
    ),
    path(
        "shortcuts/<int:shortcut_id>/<str:action>/",
        portal.shortcut_action,
        name="shortcut_action",
    ),
    path("", portal.overview, name="dashboard"),
    path("register/", views.register, name="register"),
    path("register/<str:token>/", views.register, name="register_invited"),
    path("children/new/", views.child_create, name="child_create"),
    path("children/<int:child_id>/edit/", views.child_update, name="child_update"),
    path(
        "children/<int:child_id>/blackouts/new/",
        views.blackout_create,
        name="blackout_create",
    ),
    path(
        "blackouts/<int:blackout_id>/edit/",
        views.blackout_update,
        name="blackout_update",
    ),
    path(
        "blackouts/<int:blackout_id>/deactivate/",
        views.blackout_deactivate,
        name="blackout_deactivate",
    ),
    path("contacts/new/", views.contact_create, name="contact_create"),
    path(
        "contacts/<int:contact_id>/remove/", views.contact_delete, name="contact_delete"
    ),
    path(
        "contact-permissions/new/",
        views.external_contact_permission_create,
        name="external_contact_permission_create",
    ),
    path(
        "contact-permissions/<int:permission_id>/revoke/",
        views.external_contact_permission_revoke,
        name="external_contact_permission_revoke",
    ),
    path(
        "family-permissions/request/",
        views.legacy_relationship,
        name="child_family_relationship_request",
    ),
    path(
        "family-permissions/<int:relationship_id>/approve/",
        views.legacy_relationship,
        name="child_family_relationship_approve",
    ),
    path(
        "family-permissions/<int:relationship_id>/revoke/",
        views.legacy_relationship,
        name="child_family_relationship_revoke",
    ),
    path(
        "conference-groups/new/",
        views.conference_group_create,
        name="conference_group_create",
    ),
    path(
        "conference-groups/<int:group_id>/edit/",
        views.conference_group_update,
        name="conference_group_update",
    ),
]
