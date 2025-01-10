from django.apps import apps
from django.db import models

from care.emr.models.base import EMRBaseModel
from care.emr.models.encounter import Encounter
from care.emr.models.organization import Organization
from care.emr.models.patient import Patient
from care.users.models import User


class ServiceRequest(EMRBaseModel):
    status = models.CharField(max_length=100, null=True, blank=True)
    intent = models.CharField(max_length=100, null=True, blank=True)
    priority = models.CharField(max_length=100, null=True, blank=True)

    category = models.CharField(max_length=100, null=True, blank=True)
    code = models.JSONField(default=dict, null=False, blank=False)

    do_not_perform = models.BooleanField(default=False)

    subject = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="service_request",
    )
    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.CASCADE,
        related_name="service_request",
    )

    occurrence_datetime = models.DateTimeField(null=True, blank=True)
    occurrence_timing = models.JSONField(null=True, blank=True)
    as_needed = models.BooleanField(default=False)
    as_needed_for = models.JSONField(null=True, blank=True)

    authored_on = models.DateTimeField(null=True, blank=True)
    requester = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="requested_service_request"
    )

    location = models.UUIDField(Organization, null=True, blank=True)

    note = models.TextField(null=True, blank=True)
    patient_instruction = models.TextField(null=True, blank=True)

    replaces = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True
    )

    phase = models.CharField(max_length=100, null=True, blank=True)

    def calculate_phase(self):  # noqa: PLR0911 PLR0912
        DiagnosticReport = apps.get_model("emr", "DiagnosticReport")
        Specimen = apps.get_model("emr", "Specimen")

        if not (self.category == "laboratory_procedure" and self.intent == "order"):
            return None

        if self.status == "revoked":
            return "order_cancelled"

        if DiagnosticReport.objects.filter(based_on=self.pk, status="final").exists():
            return "order_completed"

        if DiagnosticReport.objects.filter(based_on=self.pk, status="invalid").exists():
            return "result_invalid"

        if DiagnosticReport.objects.filter(
            based_on=self.pk, status="preliminary", issued__isnull=False
        ).exists():
            return "result_under_review"

        if DiagnosticReport.objects.filter(based_on=self.pk, status="partial").exists():
            return "result_under_verification"

        if Specimen.objects.filter(request=self.pk, processing__gt=[]).exists():
            return "sample_in_process"

        if Specimen.objects.filter(request=self.pk, status="unsatisfactory").exists():
            return "sample_rejected"

        if Specimen.objects.filter(request=self.pk, received_at__isnull=False).exists():
            return "sample_received_at_lab"

        if Specimen.objects.filter(
            request=self.pk, dispatched_at__isnull=False
        ).exists():
            return "sample_sent_to_lab"

        if Specimen.objects.filter(
            request=self.pk, collected_at__isnull=False
        ).exists():
            return "sample_collected"

        if self.status == "active":
            return "order_in_progress"

        if self.status == "draft":
            return "order_placed"

        return None

    def save(self, *args, **kwargs):
        self.phase = self.calculate_phase()
        super().save(*args, **kwargs)
