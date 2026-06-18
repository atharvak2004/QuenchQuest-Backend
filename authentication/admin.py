from django.contrib import admin

# Register your models here.
from .models import User
from .models import SisUser

from django.contrib.auth.admin import UserAdmin
admin.site.site_header = "Quench Quest Administration"
admin.site.site_title = "Quench Quest Admin"
admin.site.index_title = "Welcome to Quench Quest Dashboard"

@admin.register(SisUser)
class SisUserAdmin(admin.ModelAdmin):
    list_display = ("id","username", "email", "choice", "is_staff")
    list_filter = ("choice",)
    search_fields = ("username", "email")
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id","volunteer_id","name","email","phone","is_verified",)
    search_fields = ("volunteer_id","name","email","phone",)
    list_filter = ("is_verified",)
    ordering = ("-id",)
    readonly_fields = ("volunteer_id",)
