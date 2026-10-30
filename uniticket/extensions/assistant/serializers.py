from rest_framework import serializers


class StrictCharField(serializers.CharField):
    def to_internal_value(self, data):
        # Keep JSON numbers invalid rather than converting them to query strings.
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class SearchRequest(serializers.Serializer):
    query = StrictCharField(min_length=1, max_length=500, trim_whitespace=True)
