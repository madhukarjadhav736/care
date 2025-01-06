from faker import Faker
from model_bakery import baker
from rest_framework.test import APITestCase


class CareAPITestBase(APITestCase):
    fake = Faker()

    def create_user(self, **kwargs):
        from care.users.models import User

        return baker.make(User, **kwargs)

    def create_facility(self):
        pass

    def create_organization(self, **kwargs):
        from care.emr.models import Organization

        return baker.make(Organization, **kwargs)

    def create_role_with_permissions(self, permissions):
        pass

    def attach_role_organization_user(self):
        pass

    def attach_role_facility_organization_user(self):
        pass
