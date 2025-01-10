from datetime import UTC, datetime

from django.db.models import Q
from django_filters import CharFilter, FilterSet, OrderingFilter, UUIDFilter
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from pydantic import UUID4, BaseModel, Field, field_validator
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from care.emr.api.viewsets.base import EMRModelViewSet
from care.emr.api.viewsets.encounter_authz_base import EncounterBasedAuthorizationBase
from care.emr.fhir.schema.base import CodeableConcept
from care.emr.models.specimen import Specimen
from care.emr.resources.specimen.spec import (
    SpecimenCreateSpec,
    SpecimenListSpec,
    SpecimenProcessingSpec,
    SpecimenRetrieveSpec,
    SpecimenSpec,
    SpecimenUpdateSpec,
    StatusChoices,
)


class SpecimenFilters(FilterSet):
    phase = CharFilter(field_name="request__phase", lookup_expr="iexact")
    request = UUIDFilter(field_name="request__external_id")
    encounter = UUIDFilter(field_name="request__encounter__external_id")

    ordering = OrderingFilter(
        fields=(
            ("created_date", "created_date"),
            ("modified_date", "modified_date"),
        )
    )


class SpecimenViewSet(EncounterBasedAuthorizationBase, EMRModelViewSet):
    database_model = Specimen
    pydantic_model = SpecimenCreateSpec
    pydantic_update_model = SpecimenUpdateSpec
    pydantic_read_model = SpecimenListSpec
    pydantic_retrieve_model = SpecimenRetrieveSpec
    filter_backends = [DjangoFilterBackend]
    filterset_class = SpecimenFilters

    def get_object(self) -> Specimen:
        self.authorize_read_encounter()
        return get_object_or_404(
            self.get_queryset(),
            Q(external_id__iexact=self.kwargs[self.lookup_field])
            | Q(identifier=self.kwargs[self.lookup_field])
            | Q(accession_identifier=self.kwargs[self.lookup_field]),
        )

    class SpecimenCollectRequest(BaseModel):
        identifier: str | None = Field(
            default=None,
            description="The identifier assigned to the specimen while collecting, this can be barcode or any other identifier",
        )

    @extend_schema(
        request=SpecimenCollectRequest,
        responses={200: SpecimenRetrieveSpec},
        tags=["specimen"],
    )
    @action(detail=True, methods=["POST"])
    def collect(self, request, *args, **kwargs):
        data = self.SpecimenCollectRequest(**request.data)
        specimen = self.get_object()
        self.authorize_update({}, specimen)

        specimen.identifier = data.identifier
        specimen.status = StatusChoices.available
        specimen.collected_at = datetime.now(UTC)
        specimen.collected_by = request.user
        specimen.save()

        return Response(
            self.get_retrieve_pydantic_model().serialize(specimen).to_json(),
        )

    class SpecimenSendToLabRequest(BaseModel):
        lab: UUID4 = Field(
            description="The laboratory to which the specimen is being sent",
        )

    @extend_schema(
        request=SpecimenSendToLabRequest,
        responses={200: SpecimenRetrieveSpec},
        tags=["specimen"],
    )
    @action(detail=True, methods=["POST"])
    def send_to_lab(self, request, *args, **kwargs):
        data = self.SpecimenSendToLabRequest(**request.data)
        specimen = self.get_object()
        service_request = specimen.request
        self.authorize_update({}, specimen)

        service_request.location = data.lab
        specimen.dispatched_at = datetime.now(UTC)
        specimen.dispatched_by = request.user
        service_request.save()
        specimen.save()

        return Response(
            self.get_retrieve_pydantic_model().serialize(specimen).to_json(),
        )

    class SpecimenReceiveAtLabRequest(BaseModel):
        accession_identifier: str | None = Field(
            default=None,
            description="The identifier assigned to the specimen by the laboratory",
        )

        condition: list[CodeableConcept] | None = Field(
            default=None,
            description="The condition of the specimen while received at the laboratory",
        )

        note: str | None = Field(
            default=None,
            description="Comments made about the specimen while received at the laboratory",
        )

        @field_validator("condition")
        @classmethod
        def validate_condition(cls, value: CodeableConcept):
            return SpecimenSpec.validate_condition(value)

    @extend_schema(
        request=SpecimenReceiveAtLabRequest,
        responses={200: SpecimenRetrieveSpec},
        tags=["specimen"],
    )
    @action(detail=True, methods=["POST"])
    def receive_at_lab(self, request, *args, **kwargs):
        data = self.SpecimenReceiveAtLabRequest(**request.data)
        specimen = self.get_object()
        self.authorize_update({}, specimen)

        specimen.accession_identifier = data.accession_identifier
        specimen.condition = data.condition
        specimen.received_at = datetime.now(UTC)
        specimen.received_by = request.user
        specimen.note = data.note
        specimen.save()

        return Response(
            self.get_retrieve_pydantic_model().serialize(specimen).to_json(),
        )

    class SpecimenProcessRequest(BaseModel):
        process: list[SpecimenProcessingSpec] = Field(
            description="The processing steps that have been performed on the specimen",
        )

    @extend_schema(
        request=SpecimenProcessRequest,
        responses={200: SpecimenRetrieveSpec},
        tags=["specimen"],
    )
    @action(detail=True, methods=["POST"])
    def process(self, request, *args, **kwargs):
        data = self.SpecimenProcessRequest(**request.data)
        specimen = self.get_object()
        self.authorize_update({}, specimen)

        processes = []
        for process in data.process:
            if not process.time:
                process.time = datetime.now(UTC)

            if not process.performer:
                process.performer = request.user.external_id

            processes.append(process.model_dump(mode="json"))

        specimen.processing.extend(processes)
        specimen.save()

        return Response(
            self.get_retrieve_pydantic_model().serialize(specimen).to_json(),
        )
