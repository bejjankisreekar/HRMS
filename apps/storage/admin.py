from django.contrib import admin

from .models import StorageAuditLog, StoredFile, UserStorageQuota

admin.site.register(StoredFile)
admin.site.register(UserStorageQuota)
admin.site.register(StorageAuditLog)
