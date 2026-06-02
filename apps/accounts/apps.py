from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        from django.db.models.signals import post_migrate

        post_migrate.connect(_sync_staff_schema, sender=self)


def _sync_staff_schema(sender, **kwargs):
    from django.core.management import call_command

    call_command("ensure_staff_schema", verbosity=0)
