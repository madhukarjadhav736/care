from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import UUID4, Field, field_validator

from care.emr.fhir.schema.base import Coding, Timing
from care.emr.models.encounter import Encounter
from care.emr.models.service_request import ServiceRequest
from care.emr.registries.care_valueset.care_valueset import validate_valueset
from care.emr.resources.base import EMRResource
from care.emr.resources.encounter.spec import EncounterRetrieveSpec
from care.emr.resources.organization.spec import OrganizationRetrieveSpec
from care.emr.resources.patient.spec import PatientRetrieveSpec
from care.emr.resources.service_request.valueset import (
    CARE_LAB_ORDER_CODE_VALUESET,
    CARE_MEDICATION_AS_NEEDED_REASON_VALUESET,
)
from care.emr.resources.user.spec import UserSpec
from care.users.models import User


class ServiceRequestStatusChoices(str, Enum):
    draft = "draft"
    active = "active"
    on_hold = "on-hold"
    revoked = "revoked"
    completed = "completed"
    entered_in_error = "entered-in-error"
    unknown = "unknown"


class ServiceRequestIntentChoices(str, Enum):
    proposal = "proposal"
    plan = "plan"
    directive = "directive"
    order = "order"


class ServiceRequestPriorityChoices(str, Enum):
    routine = "routine"
    urgent = "urgent"
    asap = "asap"
    stat = "stat"


class ServiceRequestCategoryChoices(str, Enum):
    laboratory_procedure = "laboratory_procedure"
    imaging = "imaging"
    counselling = "counselling"
    education = "education"
    surgical_procedure = "surgical_procedure"


class ServiceRequestSpec(EMRResource):
    __model__ = ServiceRequest
    __exclude__ = ["subject", "encounter", "requester", "location", "replaces"]

    id: UUID4 | None = None

    status: ServiceRequestStatusChoices = Field(
        default=ServiceRequestStatusChoices.draft,
        description="Indicates the status of the request, used internally to track the lifecycle of the request",
    )
    intent: ServiceRequestIntentChoices = Field(
        default=ServiceRequestIntentChoices.order,
        description="Indicates the level of authority/intentionality associated with the request",
    )
    priority: ServiceRequestPriorityChoices = Field(
        default=ServiceRequestPriorityChoices.routine,
        description="Indicates the urgency of the request",
    )

    category: ServiceRequestCategoryChoices | None = Field(
        default=None,
        description="Identifies the broad category of service that is to be performed",
    )
    code: Coding = Field(
        json_schema_extra={
            "slug": CARE_LAB_ORDER_CODE_VALUESET.slug
        },  # TODO: consider using a broader value set (https://build.fhir.org/valueset-procedure-code.html)
        description="Identifies the service or product to be supplied",
    )

    do_not_perform: bool = Field(
        default=False,
        description="If true indicates that the service/procedure should NOT be performed",
    )

    subject: UUID4 = Field(
        description="The patient for whom the service/procedure is being requested",
    )
    encounter: UUID4 = Field(
        description="The encounter within which this service request was created",
    )

    occurrence_datetime: datetime | None = Field(
        default=None,
        description="The datetime at which the requested service should occur",
    )
    occurrence_timing: Timing | None = Field(
        default=None,
        description="The timing schedule for the requested service, used when the occurrence repeats",
    )
    as_needed: bool = Field(
        default=False,
        description="If true indicates that the service/procedure can be performed as needed",
    )
    as_needed_for: Coding | None = Field(
        default=None,
        json_schema_extra={"slug": CARE_MEDICATION_AS_NEEDED_REASON_VALUESET.slug},
        description="The condition under which the service/procedure should be performed",
    )

    authored_on: datetime = Field(
        default=datetime.now(UTC),
        description="The date when the request was made",
    )
    requester: UUID4 = Field(
        description="The individual who initiated the request and has responsibility for its activation",
    )

    location: UUID4 | None = Field(
        default=None,
        description="The location where the service will be performed",
    )

    note: str | None = Field(
        default=None,
        description="Comments made about the service request by the requester, performer, subject, or other participants",
    )
    patient_instruction: str | None = Field(
        default=None,
        description="Instructions for the patient on how the service should be performed",
    )

    replaces: UUID4 | None = Field(
        None,
        description="The request that is being replaced by this request, used in the case of re-orders",
    )

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str):
        return validate_valueset(
            "code", cls.model_fields["code"].json_schema_extra["slug"], value
        )

    @field_validator("as_needed_for")
    @classmethod
    def validate_as_needed_for(cls, value: str):
        return validate_valueset(
            "as_needed_for",
            cls.model_fields["as_needed_for"].json_schema_extra["slug"],
            value,
        )


class ServiceRequestCreateSpec(ServiceRequestSpec):
    def perform_extra_deserialization(self, is_update, obj):
        if not is_update:
            obj.encounter = Encounter.objects.get(external_id=self.encounter)
            obj.subject = obj.encounter.patient
            obj.requester = User.objects.get(external_id=self.requester)


class ServiceRequestUpdateSpec(ServiceRequestCreateSpec):
    class Config:
        exclude_unset = True


class ServiceRequestListSpec(ServiceRequestSpec):
    code: Coding = {}
    subject: PatientRetrieveSpec = {}
    encounter: EncounterRetrieveSpec = {}
    requester: UserSpec = {}
    location: OrganizationRetrieveSpec | None = None
    replaces: ServiceRequestRetrieveSpec | None = None

    created_by: UserSpec | None = None
    updated_by: UserSpec | None = None

    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        mapping["id"] = obj.external_id


class ServiceRequestRetrieveSpec(ServiceRequestListSpec):
    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        mapping["id"] = obj.external_id

        if obj.subject:
            mapping["subject"] = PatientRetrieveSpec.serialize(obj.subject).to_json()
        if obj.encounter:
            mapping["encounter"] = EncounterRetrieveSpec.serialize(
                obj.encounter
            ).to_json()
        if obj.requester:
            mapping["requester"] = UserSpec.serialize(obj.requester).to_json()
        if obj.location:
            mapping["location"] = OrganizationRetrieveSpec.serialize(
                obj.location
            ).to_json()
        if obj.replaces:
            mapping["replaces"] = ServiceRequestRetrieveSpec.serialize(
                obj.replaces
            ).to_json()

        if obj.created_by:
            mapping["created_by"] = UserSpec.serialize(obj.created_by).to_json()
        if obj.updated_by:
            mapping["updated_by"] = UserSpec.serialize(obj.updated_by).to_json()
