from django.contrib import admin

from .models import CareerPathStep, Designation, Grade, GradeChangeLog, GradePermission

admin.site.register(Grade)
admin.site.register(Designation)
admin.site.register(GradePermission)
admin.site.register(CareerPathStep)
admin.site.register(GradeChangeLog)
