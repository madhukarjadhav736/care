from datetime import UTC, datetime

from django_filters import CharFilter, FilterSet, OrderingFilter, UUIDFilter
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from pydantic import BaseModel, Field
from rest_framework.decorators import action
from rest_framework.response import Response

from care.emr.api.viewsets.base import EMRModelViewSet
from care.emr.models.diagnostic_report import DiagnosticReport
from care.emr.models.observation import Observation
from care.emr.resources.diagnostic_report.spec import (
    DiagnosticReportCreateSpec,
    DiagnosticReportListSpec,
    DiagnosticReportRetrieveSpec,
    DiagnosticReportUpdateSpec,
    StatusChoices,
)
from care.emr.resources.observation.spec import (
    ObservationSpec,
    Performer,
    PerformerType,
)


class DiagnosticReportFilters(FilterSet):
    phase = CharFilter(field_name="based_on__phase", lookup_expr="iexact")
    status = CharFilter(field_name="status", lookup_expr="iexact")
    specimen = UUIDFilter(field_name="specimen__external_id")
    based_on = UUIDFilter(field_name="based_on__external_id")

    ordering = OrderingFilter(
        fields=(
            ("created_date", "created_date"),
            ("modified_date", "modified_date"),
        )
    )


class DiagnosticReportViewSet(EMRModelViewSet):
    database_model = DiagnosticReport
    pydantic_model = DiagnosticReportCreateSpec
    pydantic_update_model = DiagnosticReportUpdateSpec
    pydantic_read_model = DiagnosticReportListSpec
    pydantic_retrieve_model = DiagnosticReportRetrieveSpec
    filter_backends = [DjangoFilterBackend]
    filterset_class = DiagnosticReportFilters

    def perform_create(self, instance):
        instance.performer = self.request.user
        super().perform_create(instance)

    class DiagnosticReportObservationRequest(BaseModel):
        observations: list[ObservationSpec] = Field(
            default=[],
            description="List of observations that are part of the diagnostic report",
        )

    @extend_schema(
        request=DiagnosticReportObservationRequest,
        responses={200: DiagnosticReportRetrieveSpec},
        tags=["diagnostic_report"],
    )
    @action(detail=True, methods=["POST"])
    def observations(self, request, *args, **kwargs):
        data = self.DiagnosticReportObservationRequest(**request.data)
        report: DiagnosticReport = self.get_object()

        observations = []
        for observation in data.observations:
            if not observation.performer:
                observation.performer = Performer(
                    type=PerformerType.user,
                    id=str(request.user.external_id),
                )

            observation_instance = observation.de_serialize()
            observation_instance.subject_id = report.subject.id
            observation_instance.encounter = report.encounter
            observation_instance.patient = report.subject

            observations.append(observation_instance)

        observation_instances = Observation.objects.bulk_create(observations)
        report.result.set(observation_instances)
        report.status = StatusChoices.partial
        report.save()

        return Response(
            self.get_retrieve_pydantic_model().serialize(report).to_json(),
        )

    class DiagnosticReportVerifyRequest(BaseModel):
        is_approved: bool = Field(
            description="Indicates whether the diagnostic report is approved or rejected",
        )

    @extend_schema(
        request=DiagnosticReportVerifyRequest,
        responses={200: DiagnosticReportRetrieveSpec},
        tags=["diagnostic_report"],
    )
    @action(detail=True, methods=["POST"])
    def verify(self, request, *args, **kwargs):
        data = self.DiagnosticReportVerifyRequest(**request.data)
        report: DiagnosticReport = self.get_object()

        if data.is_approved:
            report.status = StatusChoices.preliminary
        else:
            report.status = StatusChoices.cancelled

        report.issued = datetime.now(UTC)
        report.save()

        return Response(
            self.get_retrieve_pydantic_model().serialize(report).to_json(),
        )

    class DiagnosticReportReviewRequest(BaseModel):
        is_approved: bool = Field(
            description="Indicates whether the diagnostic report is approved or rejected",
        )
        conclusion: str | None = Field(
            default=None,
            description="Additional notes about the review",
        )

    @extend_schema(
        request=DiagnosticReportReviewRequest,
        responses={200: DiagnosticReportRetrieveSpec},
        tags=["diagnostic_report"],
    )
    @action(detail=True, methods=["POST"])
    def review(self, request, *args, **kwargs):
        data = self.DiagnosticReportReviewRequest(**request.data)
        report: DiagnosticReport = self.get_object()

        if (
            report.results_interpreter
            and report.results_interpreter.external_id != request.user.external_id
        ):
            return Response(
                {"detail": "This report is assigned to a different user for review."},
                status=403,
            )

        if data.is_approved:
            report.status = StatusChoices.final
        else:
            report.status = StatusChoices.cancelled

        report.conclusion = data.conclusion
        report.results_interpreter = request.user
        report.save()

        return Response(
            self.get_retrieve_pydantic_model().serialize(report).to_json(),
        )
