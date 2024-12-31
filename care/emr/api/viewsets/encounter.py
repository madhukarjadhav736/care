from django.db import transaction
from django_filters import rest_framework as filters
from pydantic import UUID4, BaseModel
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from care.emr.api.viewsets.base import (
    EMRBaseViewSet,
    EMRCreateMixin,
    EMRListMixin,
    EMRRetrieveMixin,
    EMRUpdateMixin,
)
from care.emr.models import (
    Encounter,
    EncounterOrganization,
    FacilityOrganization,
    Patient,
)
from care.emr.resources.encounter.constants import COMPLETED_CHOICES
from care.emr.resources.encounter.spec import (
    EncounterCreateSpec,
    EncounterListSpec,
    EncounterRetrieveSpec,
    EncounterUpdateSpec,
)
from care.emr.resources.facility_organization.spec import FacilityOrganizationReadSpec
from care.facility.models import Facility
from care.security.authorization import AuthorizationController


class LiveFilter(filters.CharFilter):
    def filter(self, qs, value):
        queryset = qs
        if not value:
            return queryset
        if value.lower() == "true":
            queryset = queryset.filter(status__in=COMPLETED_CHOICES)
        elif value.lower() == "false":
            queryset = queryset.exclude(status__in=COMPLETED_CHOICES)
        return queryset


class EncounterFilters(filters.FilterSet):
    facility = filters.UUIDFilter(field_name="facility__external_id")
    status = filters.CharFilter(field_name="status", lookup_expr="iexact")
    id = filters.UUIDFilter(field_name="external_id")
    encounter_class = filters.CharFilter(
        field_name="encounter_class", lookup_expr="iexact"
    )
    priority = filters.CharFilter(field_name="priority", lookup_expr="iexact")
    external_identifier = filters.CharFilter(
        field_name="external_identifier", lookup_expr="icontains"
    )
    phone_number = filters.CharFilter(
        field_name="patient__phone_number", lookup_expr="icontains"
    )
    name = filters.CharFilter(field_name="patient__name", lookup_expr="icontains")
    live = LiveFilter()


class EncounterViewSet(
    EMRCreateMixin, EMRRetrieveMixin, EMRUpdateMixin, EMRListMixin, EMRBaseViewSet
):
    database_model = Encounter
    pydantic_model = EncounterCreateSpec
    pydantic_update_model = EncounterUpdateSpec
    pydantic_read_model = EncounterListSpec
    pydantic_retrieve_model = EncounterRetrieveSpec
    filterset_class = EncounterFilters
    filter_backends = [filters.DjangoFilterBackend]

    def perform_create(self, instance):
        with transaction.atomic():
            organizations = getattr(instance, "_organizations", [])
            super().perform_create(instance)
            for organization in organizations:
                EncounterOrganization.objects.create(
                    encounter=instance,
                    organization=get_object_or_404(
                        FacilityOrganization,
                        external_id=organization,
                        facility=instance.facility,
                    ),
                )
            if not organizations:
                instance.sync_organization_cache()

    def authorize_update(self, request_obj, model_instance):
        if not AuthorizationController.call(
            "can_update_encounter_obj", self.request.user, model_instance
        ):
            raise PermissionDenied("You do not have permission to update encounter")

    def authorize_create(self, instance):
        # Check if encounter create permission exists on Facility Organization
        facility = get_object_or_404(Facility, external_id=instance.facility)
        if not AuthorizationController.call(
            "can_create_encounter_obj", self.request.user, facility
        ):
            raise PermissionDenied("You do not have permission to create encounter")

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("patient", "facility", "appointment")
            .order_by("-created_date")
        )
        if (
            self.action in ["list", "retrieve"]
            and "patient" in self.request.GET
            and self.request.GET["patient"]
        ):
            # If the user has view access to the patient, then encounter view is also granted for that patient
            patient = get_object_or_404(
                Patient, external_id=self.request.GET["patient"]
            )
            if AuthorizationController.call(
                "can_view_patient_obj", self.request.user, patient
            ):
                return qs.filter(patient=patient)
            raise PermissionDenied("User Cannot access patient")

        if (
            self.action in ["list", "retrieve"]
            and "facility" in self.request.GET
            and self.request.GET["facility"]
        ):
            # If the user has view access to the patient, then encounter view is also granted for that patient
            facility = get_object_or_404(
                Facility, external_id=self.request.GET["facility"]
            )
            return AuthorizationController.call(
                "get_filtered_encounters", qs, self.request.user, facility
            )
        if self.action in ["list", "retrieve"]:
            raise PermissionDenied("Cannot access encounters")
        return qs  # Authz Exists separately for update and deletes

    @action(detail=True, methods=["GET"])
    def organizations(self, request, *args, **kwargs):
        instance = self.get_object()
        self.authorize_update({}, instance)
        encounter_organizations = EncounterOrganization.objects.filter(
            encounter=instance
        ).select_related("organization")
        data = [
            FacilityOrganizationReadSpec.serialize(
                encounter_organization.organization
            ).to_json()
            for encounter_organization in encounter_organizations
        ]
        return Response({"results": data})

    class EncounterOrganizationManageSpec(BaseModel):
        organization: UUID4

    @action(detail=True, methods=["POST"])
    def organizations_add(self, request, *args, **kwargs):
        instance = self.get_object()
        self.authorize_update({}, instance)
        request_data = self.EncounterOrganizationManageSpec(**request.data)
        organization = get_object_or_404(
            FacilityOrganization, external_id=request_data.organization
        )
        if organization.facility.id != instance.facility.id:
            raise PermissionDenied("Organization Incompatible with Encounter")
        encounter_organization = EncounterOrganization.objects.filter(
            encounter=instance, organization=organization
        )
        if encounter_organization.exists():
            raise ValidationError("Organization already exists")
        EncounterOrganization.objects.create(
            encounter=instance, organization=organization
        )
        return Response(FacilityOrganizationReadSpec.serialize(organization).to_json())

    @action(detail=True, methods=["DELETE"])
    def organizations_remove(self, request, *args, **kwargs):
        instance = self.get_object()
        self.authorize_update({}, instance)
        request_data = self.EncounterOrganizationManageSpec(**request.data)
        organization = get_object_or_404(
            FacilityOrganization, external_id=request_data.organization
        )
        if organization.facility.id != instance.facility.id:
            raise PermissionDenied("Organization Incompatible with Encounter")
        encounter_organization = EncounterOrganization.objects.filter(
            encounter=instance, organization=organization
        )
        if not encounter_organization.exists():
            raise ValidationError("Organization does not exist")
        EncounterOrganization.objects.filter(
            encounter=instance, organization=organization
        ).delete()
        return Response({}, status=204)
