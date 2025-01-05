from django.db import models

from care.emr.models.base import EMRBaseModel
from care.emr.models.encounter import Encounter
from care.emr.models.observation import Observation
from care.emr.models.patient import Patient
from care.emr.models.service_request import ServiceRequest
from care.emr.models.specimen import Specimen
from care.users.models import User


class DiagnosticReport(EMRBaseModel):
    status = models.CharField(max_length=100, null=True, blank=True)

    category = models.JSONField(null=True, blank=True)
    code = models.JSONField(default=dict, null=False, blank=False)

    based_on = models.ForeignKey(
        ServiceRequest, on_delete=models.CASCADE, related_name="diagnostic_report"
    )  # TODO: Make it GenericForeignKey when needed
    subject = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="diagnostic_report",
    )
    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.CASCADE,
        related_name="diagnostic_report",
    )

    performer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="performed_diagnostic_report",
    )
    results_interpreter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="interpreted_diagnostic_report",
    )

    issued = models.DateTimeField(null=True, blank=True)
    effective_period = models.JSONField(null=True, blank=True)

    specimen = models.ManyToManyField(
        Specimen, blank=True, related_name="diagnostic_report"
    )
    result = models.ManyToManyField(
        Observation, blank=True, related_name="diagnostic_report"
    )

    media = models.JSONField(default=list, null=True, blank=True)

    note = models.TextField(null=True, blank=True)
    conclusion = models.TextField(null=True, blank=True)
