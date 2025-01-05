from enum import Enum

from pydantic.main import BaseModel

from care.emr.fhir.resources.base import ResourceManger
from care.emr.fhir.utils import parse_fhir_parameter_output


class ConceptMapResource(ResourceManger):
    allowed_properties = ["system", "code"]
    resource = "ConceptMap"

    def serialize_lookup(self, result):
        structured_output = parse_fhir_parameter_output(result)

        return ConceptMapResult(
            result=structured_output.get("metadata", {}).get("result", False),
            match=[
                ConceptMapMatch(
                    equivalence=match.get("equivalence"),
                    concept=ConceptMapConcept(
                        display=match.get("concept", {}).get("display"),
                        code=match.get("concept", {}).get("code"),
                    ),
                    source=match["source"],
                )
                for match in structured_output.get("match", [])
            ],
        )

    def translate(self):
        if "system" not in self._filters or "code" not in self._filters:
            err = "Both system and code are required"
            raise ValueError(err)
        full_result = self.query("GET", "ConceptMap/$translate", self._filters)

        return self.serialize_lookup(full_result["parameter"])


class ConceptMapConcept(BaseModel):
    display: str
    code: str


class ConceptMapEquivalence(str, Enum):
    def __new__(cls, value, priority=None):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.priority = priority
        return obj

    # This is the strongest form of equality.
    equal = "equal", 1

    # Indicates equivalence, almost identical.
    equivalent = "equivalent", 2

    # Concepts are related, exact nature unspecified.
    relatedto = "relatedto", 3

    # The source concept is more specific than the target.
    specializes = "specializes", 4

    # The source concept is more general and subsumes the target.
    subsumes = "subsumes", 5

    # The source is broader in meaning than the target.
    wider = "wider", 6

    # The source is narrower in meaning than the target.
    narrower = "narrower", 7

    # The relationship is approximate but not exact.
    inexact = "inexact", 8

    # Indicates a complete lack of relationship or overlap.
    disjoint = "disjoint", 9

    # No match exists for the source concept in the target system.
    unmatched = "unmatched", 10


class ConceptMapMatch(BaseModel):
    equivalence: ConceptMapEquivalence
    concept: ConceptMapConcept
    source: str


class ConceptMapResult(BaseModel):
    result: bool
    match: list[ConceptMapMatch]
