from django.conf import settings

from uni_ticket.settings import (
    EMPLOYEE_ATTRIBUTE_NAME,
    USER_ATTRIBUTE_NAME,
)

def _get_identifier(user):
    # Try getting the employee identifier.
    identifier = getattr(user, EMPLOYEE_ATTRIBUTE_NAME, None)
    if identifier:
        return (int(identifier), True)

    # Try getting the user identifier.
    identifier = getattr(user, USER_ATTRIBUTE_NAME, None)
    if identifier:
        return (int(identifier), False)

    raise Exception("Could not find user identifier")

def get_user_context(request):
    try:
        user_identifier, user_is_employee = _get_identifier(request.user)

        return {
            "user_first_name" : request.user.first_name,
            "user_last_name" : request.user.last_name,
            "user_email" : request.user.email,
            "user_identifier" : user_identifier,
            "user_is_employee" : user_is_employee
        }
    except:
        return {}
