from django.db import models

# Create your models here.


class OurImpact(models.Model):

    children_women_supported = models.PositiveIntegerField()
    skill_awareness_programs = models.PositiveIntegerField()
    communities_reached = models.PositiveIntegerField()

    date = models.DateField()

    def __str__(self):
        return f"Impact - {self.date}"


class Leadership(models.Model):

    image = models.ImageField(upload_to="leadership/")

    name = models.CharField(max_length=100)

    position = models.CharField(max_length=100)

    short_description = models.TextField()

    def __str__(self):
        return self.name



class ProgramCard(models.Model):

    icon = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    title = models.CharField(max_length=200)
    description = models.TextField()
    activities = models.CharField(max_length=200,default="Key Activities:")
    activity_points = models.TextField(help_text="Separate values using commas")
    target = models.CharField(max_length=200,default="Target Beneficiaries:")
    benefits = models.TextField(help_text="Separate values using commas")

    def __str__(self):
        return self.title


