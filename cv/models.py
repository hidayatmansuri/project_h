from django.db import models

# Create your models here.

class PersonalInfo(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.IntegerField()
    address = models.CharField(max_length=200)
    profile = models.TextField()
    
    def __str__(self):
        return self.name

class Qualification(models.Model):
    institute = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    degree = models.CharField(max_length=100)
    subject = models.TextField()
    
    def __str__(self):
        return self.institute
class Experience(models.Model):
    title = models.CharField(max_length=100)
    employer = models.CharField(max_length=100)
    industry = models.CharField(max_length=30)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField()

    def __str__(self):
        return self.title

