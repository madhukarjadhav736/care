from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.exceptions import ValidationError

from care.emr.fhir.resources.code_concept import CodeConceptResource
from care.emr.fhir.resources.concept_map import ConceptMapResource
from care.emr.models.service_request import ServiceRequest
from care.emr.resources.specimen.spec import SpecimenCreateSpec


@receiver(post_save, sender=ServiceRequest)
def create_specimen(sender, instance: ServiceRequest, created: bool, **kwargs):
    """
    Auto create a Specimen resource when a ServiceRequest is created.

    TODO: Change the trigger later to when the billing is done.
    """

    if not created:
        return None

    code_concept = (
        CodeConceptResource()
        .filter(system="http://loinc.org", code=instance.code.get("code"))
        .get()
    )

    loinc_specimen_code = (
        code_concept.get("properties", {}).get("system-core", {}).get("code")
    )
    concept_map = (
        ConceptMapResource()
        .filter(system="http://loinc.org", code=loinc_specimen_code)
        .translate()
    )

    specimen_matches = list(
        filter(
            lambda x: "(specimen)" in x.concept.display,
            concept_map.match,
        )
    )
    specimen_matches.sort(key=lambda x: x.equivalence.priority)

    if len(specimen_matches) == 0:
        return ValidationError(
            f"No Specimen found for the given Service Request code {instance.code}"
        )

    specimen_coding = specimen_matches[0].concept

    specimen = SpecimenCreateSpec(
        type={
            "code": specimen_coding.code,
            "display": specimen_coding.display,
            "system": "http://snomed.info/sct",
        },
        request=instance.external_id,
        subject=instance.subject.external_id,
    ).de_serialize()
    specimen.save()

    return specimen
