from datetime import UTC, datetime

from django.db import models
from django.db.models import Case, CharField, Value, When
from django_filters import ChoiceFilter, FilterSet, OrderingFilter, UUIDFilter
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.response import Response

from care.emr.api.viewsets.base import EMRModelViewSet
from care.emr.models.diagnostic_report import DiagnosticReport
from care.emr.models.observation import Observation
from care.emr.resources.diagnostic_report.spec import (
    DiagnosticReportCreateSpec,
    DiagnosticReportListSpec,
    DiagnosticReportObservationRequest,
    DiagnosticReportRetrieveSpec,
    DiagnosticReportReviewRequest,
    DiagnosticReportUpdateSpec,
    DiagnosticReportVerifyRequest,
    StatusChoices,
)
from care.emr.resources.observation.spec import Performer, PerformerType


class PhaseChoices(models.TextChoices):
    IN_PROCESS = "in_process", "In Process"
    VERIFICATION_REQUIRED = "verification_required", "Verification Required"
    REVIEW_REQUIRED = "review_required", "Review Required"
    REVIEWED = "reviewed", "Reviewed"


class DiagnosticReportFilters(FilterSet):
    phase = ChoiceFilter(choices=PhaseChoices.choices, method="filter_phase")
    status = ChoiceFilter(
        choices=[(status.value, status.value) for status in StatusChoices]
    )
    specimen = UUIDFilter(field_name="specimen__external_id")
    based_on = UUIDFilter(field_name="based_on__external_id")

    ordering = OrderingFilter(
        fields=(
            ("created_date", "created_date"),
            ("modified_date", "modified_date"),
        )
    )

    def filter_phase(self, queryset, name, value):
        return queryset.annotate(
            phase=Case(
                When(status=StatusChoices.final, then=Value("reviewed")),
                When(status=StatusChoices.preliminary, then=Value("review_required")),
                When(status=StatusChoices.partial, then=Value("verification_required")),
                default=Value("in_process"),
                output_field=CharField(),
            )
        ).filter(phase=value)


@extend_schema_view(
    create=extend_schema(request=DiagnosticReportCreateSpec),
    update=extend_schema(request=DiagnosticReportUpdateSpec),
    list=extend_schema(request=DiagnosticReportListSpec),
    retrieve=extend_schema(request=DiagnosticReportRetrieveSpec),
)
class DiagnosticReportViewSet(EMRModelViewSet):
    database_model = DiagnosticReport
    pydantic_model = DiagnosticReportCreateSpec
    pydantic_update_model = DiagnosticReportUpdateSpec
    pydantic_read_model = DiagnosticReportListSpec
    pydantic_retrieve_model = DiagnosticReportRetrieveSpec
    filter_backends = [DjangoFilterBackend]
    filterset_class = DiagnosticReportFilters

    def clean_create_data(self, request, *args, **kwargs):
        clean_data = super().clean_create_data(request, *args, **kwargs)

        clean_data["performer"] = self.request.user.external_id
        return clean_data

    @extend_schema(
        request=DiagnosticReportObservationRequest,
        responses={200: DiagnosticReportRetrieveSpec},
        tags=["diagnostic_report"],
    )
    @action(detail=True, methods=["POST"])
    def observations(self, request, *args, **kwargs):
        data = DiagnosticReportObservationRequest(**request.data)
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

    @extend_schema(
        request=DiagnosticReportVerifyRequest,
        responses={200: DiagnosticReportRetrieveSpec},
        tags=["diagnostic_report"],
    )
    @action(detail=True, methods=["POST"])
    def verify(self, request, *args, **kwargs):
        data = DiagnosticReportVerifyRequest(**request.data)
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

    @extend_schema(
        request=DiagnosticReportReviewRequest,
        responses={200: DiagnosticReportRetrieveSpec},
        tags=["diagnostic_report"],
    )
    @action(detail=True, methods=["POST"])
    def review(self, request, *args, **kwargs):
        data = DiagnosticReportReviewRequest(**request.data)
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
