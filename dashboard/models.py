# from django.db import models
from authentication.models import User


# class Campaign(models.Model):
#     title = models.CharField(max_length=200)
#     description = models.TextField()
#     is_active = models.BooleanField(default=True)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return self.title


# from authentication.models import User

# class Beneficiary(models.Model):
#     user = models.ForeignKey(User,on_delete=models.CASCADE,null=True,blank=True)
#     age = models.IntegerField(null=True, blank=True)
#     need = models.CharField(max_length=255, default="Not specified")
#     location = models.CharField(max_length=255, default="Unknown")
#     status = models.CharField(
#         max_length=20,
#         choices=[
#             ("pending", "Pending"),
#             ("approved", "Approved"),
#             ("helped", "Helped")
#         ],
#         default="pending"
#     )
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return self.user.name

# class Donation(models.Model):
#     donor = models.ForeignKey(User, on_delete=models.CASCADE)
#     amount = models.DecimalField(max_digits=10, decimal_places=2)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.donor.name} - {self.amount}"