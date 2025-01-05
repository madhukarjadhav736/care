from django_filters import FilterSet, OrderingFilter, UUIDFilter
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from care.emr.api.viewsets.base import EMRModelViewSet
from care.emr.models.service_request import ServiceRequest
from care.emr.resources.service_request.spec import (
    ServiceRequestCreateSpec,
    ServiceRequestListSpec,
    ServiceRequestRetrieveSpec,
    ServiceRequestUpdateSpec,
)


class ServiceRequestFilters(FilterSet):
    subject = UUIDFilter(field_name="subject__external_id")
    encounter = UUIDFilter(field_name="encounter__external_id")

    ordering = OrderingFilter(
        fields=(
            ("created_date", "created_date"),
            ("modified_date", "modified_date"),
        )
    )


@extend_schema_view(
    create=extend_schema(request=ServiceRequestCreateSpec),
    update=extend_schema(request=ServiceRequestUpdateSpec),
    list=extend_schema(request=ServiceRequestListSpec),
    retrieve=extend_schema(request=ServiceRequestRetrieveSpec),
)
class ServiceRequestViewSet(EMRModelViewSet):
    database_model = ServiceRequest
    pydantic_model = ServiceRequestCreateSpec
    pydantic_update_model = ServiceRequestUpdateSpec
    pydantic_read_model = ServiceRequestListSpec
    pydantic_retrieve_model = ServiceRequestRetrieveSpec
    filter_backends = [DjangoFilterBackend]
    filterset_class = ServiceRequestFilters

    def clean_create_data(self, request, *args, **kwargs):
        clean_data = super().clean_create_data(request, *args, **kwargs)

        clean_data["requester"] = self.request.user.external_id
        return clean_data
