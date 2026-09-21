from django.contrib import admin
from .models import PersonalInfo, Qualification, Experience, Skill

# Register your models here.
admin.site.register(PersonalInfo)
admin.site.register(Qualification)
admin.site.register(Experience)
admin.site.register(Skill)
