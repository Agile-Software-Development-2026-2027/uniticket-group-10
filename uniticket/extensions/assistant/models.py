import uuid

from django.conf import settings
from django.db import models


class AssistantThread(models.Model):
    """Associate an assistant conversation with its owner.

    Django creates the conversation ID and checks ownership before forwarding
    requests to the agent. Messages and agent state are stored separately.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistant_threads",
    )
    created_at = models.DateTimeField(auto_now_add=True)
