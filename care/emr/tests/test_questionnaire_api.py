from django.urls import reverse

from care.utils.tests.base import CareAPITestBase


class BaseQuestionnaireTest(CareAPITestBase):
    """
    Base test class providing common functionality for questionnaire testing.
    """

    def setUp(self):
        super().setUp()
        self.user = self.create_super_user()
        self.facility = self.create_facility(user=self.user)
        self.organization = self.create_organization(org_type="govt")
        self.patient = self.create_patient()
        self.client.force_authenticate(user=self.user)

        self.base_url = reverse("questionnaire-list")
        self.questionnaire_data = self._create_questionnaire()
        self.questions = self.questionnaire_data.get("questions", [])

    def _submit_questionnaire(self, payload):
        """
        Helper to submit a questionnaire and return response details.
        """
        submit_url = reverse(
            "questionnaire-submit", kwargs={"slug": self.questionnaire_data["slug"]}
        )
        response = self.client.post(submit_url, payload, format="json")
        return response.status_code, response.json()

    def _get_question_by_type(self, q_type):
        """
        Helper to retrieve a question of specific type from the questionnaire.
        """
        return next(q for q in self.questions if q["type"] == q_type)

    def _create_base_payload(self, question_id, value):
        """
        Creates a basic payload structure for questionnaire submission.
        """
        return {
            "resource_id": str(self.patient.external_id),
            "patient": str(self.patient.external_id),
            "results": [{"question_id": question_id, "values": [{"value": value}]}],
        }


class TestQuestionnaireViewSet(BaseQuestionnaireTest):
    """
    Test suite for questionnaire submission with various question types.
    Tests both valid and invalid submissions for each question type.
    """

    def _create_questionnaire(self):
        """
        Creates a test questionnaire with multiple question types.
        """
        # Define question templates for different types
        question_templates = {
            "base": {
                "code": {
                    "display": "Test Value",
                    "system": "http://test_system.care/test",
                    "code": "123",
                }
            },
            "choice": {
                "answer_option": [
                    {"value": "EXCESSIVE", "display": "Excessive"},
                    {"value": "SATISFACTORY", "display": "Satisfactory"},
                    {"value": "UNSATISFACTORY", "display": "Unsatisfactory"},
                    {"value": "NO_SLEEP", "display": "No sleep"},
                ]
            },
        }

        # Define questions with their specific attributes
        questions = [
            {
                "link_id": "1",
                "type": "boolean",
                "text": "Are you experiencing symptoms?",
            },
            {"link_id": "2", "type": "decimal", "text": "Body temperature"},
            {"link_id": "3", "type": "integer", "text": "Days unwell"},
            {"link_id": "4", "type": "string", "text": "Name"},
            {"link_id": "5", "type": "text", "text": "Symptom description"},
            {"link_id": "6", "type": "display", "text": "Thank you message"},
            {"link_id": "7", "type": "date", "text": "Symptom onset date"},
            {"link_id": "8", "type": "dateTime", "text": "Precise onset time"},
            {"link_id": "9", "type": "time", "text": "Last meal time"},
            {"link_id": "10", "type": "url", "text": "Health profile link"},
            {"link_id": "11", "type": "structured", "text": "Structured input"},
            {
                "link_id": "12",
                "type": "choice",
                "text": "Sleep pattern",
                **question_templates["choice"],
            },
        ]

        # Add base template to all questions
        for question in questions:
            question.update(question_templates["base"])

        data = {
            "title": "Multi-Type Test",
            "slug": "doctor-test-multi-type",
            "description": "Test questionnaire with various question types",
            "status": "active",
            "subject_type": "patient",
            "organizations": [str(self.organization.external_id)],
            "questions": questions,
        }

        response = self.client.post(self.base_url, data, format="json")
        self.assertEqual(
            response.status_code,
            200,
            f"Questionnaire creation failed: {response.json()}",
        )
        return response.json()

    def _get_valid_value_for_type(self, q_type):
        """
        Returns a valid test value for each question type.
        """
        valid_values = {
            "boolean": "true",
            "decimal": "65.5",
            "integer": "65",
            "string": "John Doe",
            "text": "Feeling unwell",
            "date": "2023-12-31",
            "dateTime": "2023-12-31T15:30:00",
            "time": "15:30:00",
            "choice": "EXCESSIVE",
            "url": "http://example.com",
            "structured": "Structured Value",
        }
        return valid_values.get(q_type)

    def _get_invalid_value_for_type(self, q_type):
        """
        Returns an invalid test value for each question type.
        """
        invalid_values = {
            "boolean": "not_boolean",
            "decimal": "abc",
            "integer": "123.45",
            "date": "invalid-date",
            "dateTime": "01-16-2025T10:30:00",
            "time": "25:61:00",
            "choice": "NOT_A_VALID_CHOICE",
            "url": "example.com",
        }
        return invalid_values.get(q_type)

    def test_submit_all_questions_valid(self):
        """Tests submission with valid values for all question types."""
        results = []
        for question in self.questions:
            if question["type"] != "display":
                value = self._get_valid_value_for_type(question["type"])
                if value:
                    results.append(
                        {"question_id": question["id"], "values": [{"value": value}]}
                    )

        payload = {
            "resource_id": str(self.patient.external_id),
            "patient": str(self.patient.external_id),
            "results": results,
        }

        status_code, json_resp = self._submit_questionnaire(payload)
        self.assertEqual(status_code, 200, f"Valid submission failed: {json_resp}")

    def test_invalid_submissions(self):
        """Tests invalid submissions for each question type."""
        test_types = [
            "boolean",
            "decimal",
            "integer",
            "date",
            "dateTime",
            "time",
            "choice",
            "url",
        ]

        for q_type in test_types:
            question = self._get_question_by_type(q_type)
            invalid_value = self._get_invalid_value_for_type(q_type)

            payload = self._create_base_payload(question["id"], invalid_value)
            status_code, json_resp = self._submit_questionnaire(payload)

            with self.subTest(q_type=q_type):
                self.assertEqual(status_code, 400)
                self.assertIn("errors", json_resp)
                error = json_resp["errors"][0]
                self.assertEqual(error["type"], "type_error")
                self.assertEqual(error["question_id"], question["id"])
                self.assertIn(f"Invalid {q_type}", error["msg"])


class TestQuestionnaireRequiredFields(BaseQuestionnaireTest):
    """Test suite for required field validation in questionnaires."""

    def _create_questionnaire(self):
        """Creates a questionnaire with required fields for testing."""
        data = {
            "title": "Required Fields Test",
            "slug": "required-fields-test",
            "description": "Test questionnaire with required fields",
            "status": "active",
            "subject_type": "patient",
            "organizations": [str(self.organization.external_id)],
            "questions": [
                {
                    "link_id": "1",
                    "type": "boolean",
                    "text": "Required question",
                    "required": True,
                    "code": {
                        "display": "Test Value",
                        "system": "http://test_system.care/test",
                        "code": "123",
                    },
                }
            ],
        }

        response = self.client.post(self.base_url, data, format="json")
        self.assertEqual(
            response.status_code,
            200,
            f"Questionnaire creation failed: {response.json()}",
        )
        return response.json()

    def test_required_field_validation(self):
        """Tests validation of required fields."""
        question = self.questions[0]
        payload = self._create_base_payload(question["id"], None)
        payload["results"][0]["values"] = []

        status_code, json_resp = self._submit_questionnaire(payload)

        self.assertEqual(status_code, 400)
        self.assertIn("errors", json_resp)
        error = json_resp["errors"][0]
        self.assertEqual(error["type"], "values_missing")
        self.assertEqual(error["question_id"], question["id"])
        self.assertIn("No value provided for question", error["msg"])


# Todo: Add test for recursive required check and group type
