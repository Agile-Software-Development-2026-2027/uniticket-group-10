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
        identifier, is_employee = _get_identifier(request.user)

        return {
            "first_name" : request.user.first_name,
            "last_name" : request.user.last_name,
            "email" : request.user.email,
            "identifier" : identifier,
            "is_employee" : is_employee
        }
    except:
        return {}
