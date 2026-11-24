from datetime import date

from django.test import TestCase
from django.urls import reverse

from .models import Experience, PersonalInfo, Qualification, Skill


class CVViewTests(TestCase):
    def test_cv_renders_publicly_with_project_h_showcase_when_empty(self):
        response = self.client.get(reverse("cv"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "cv.html")
        self.assertTemplateUsed(response, "home.html")
        self.assertContains(response, "cv.css")
        self.assertContains(response, "cv-charts.js")
        self.assertContains(response, "cvRadarChart")
        self.assertContains(response, "cvSkillsChart")
        self.assertContains(response, "Project H")
        self.assertTrue(response.context["using_default_skills"])
        self.assertGreaterEqual(len(response.context["project_showcase"]), 7)

    def test_cv_renders_profile_experience_qualification_and_skills(self):
        PersonalInfo.objects.create(
            name="Alex Example",
            email="alex@example.com",
            phone="07000000000",
            address="London, UK",
            profile="Software engineer focused on Python and Django.",
        )
        Experience.objects.create(
            title="Senior Developer",
            employer="Acme Corp",
            industry="Technology",
            start_date=date(2023, 1, 1),
            end_date=date(2025, 1, 1),
            description="Built resilient web platforms.",
        )
        Qualification.objects.create(
            institute="Example University",
            start_date=date(2018, 9, 1),
            end_date=date(2021, 6, 1),
            degree="BSc Computer Science",
            subject="Algorithms and Systems",
        )
        Skill.objects.create(
            name="Django",
            category="Backend",
            proficiency="Expert",
        )

        response = self.client.get(reverse("cv"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["using_default_skills"])
        self.assertContains(response, "Alex Example")
        self.assertContains(response, "Senior Developer")
        self.assertContains(response, "BSc Computer Science")
        self.assertContains(response, "Django")
        self.assertContains(response, "Expert")
        self.assertContains(response, "cvExperienceChart")

        payload = response.context["cv_chart_payload"]
        self.assertEqual(payload["radar_labels"], ["Backend"])
        self.assertEqual(payload["radar_values"], [95.0])
        self.assertEqual(len(payload["timeline_labels"]), 1)
