from rest_framework import serializers

from .models import Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "organization_code",
            "schema_name",
            "organization_type",
            "website",
            "industry",
            "official_email",
            "official_phone",
            "is_active",
            "created_at",
            "updated_at",
        ]

