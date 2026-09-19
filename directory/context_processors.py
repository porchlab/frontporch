from django.conf import settings


def portal(request):
    parent = (
        getattr(request.user, "frontporch_parent", None)
        if request.user.is_authenticated
        else None
    )
    return {
        "portal_parent": parent if parent and parent.is_guardian else None,
        "portal_timezone": settings.TIME_ZONE,
        "portal_allow_registration": settings.FRONTPORCH_ALLOW_REGISTRATION,
    }
