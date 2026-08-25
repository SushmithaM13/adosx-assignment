from django.contrib import admin

from .models import Location, Org, SystemARecord, SystemBEntry


@admin.register(Org)
class OrgAdmin(admin.ModelAdmin):
    list_display = ["org_id"]


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ["location_id", "org", "name"]
    list_filter = ["org"]


@admin.register(SystemARecord)
class SystemARecordAdmin(admin.ModelAdmin):
    list_display = ["record_id", "location", "total_value", "state", "has_issues"]
    list_filter = ["location__org", "state"]
    search_fields = ["record_id"]

    @admin.display(boolean=True)
    def has_issues(self, obj):
        return bool(obj.import_issues)


@admin.register(SystemBEntry)
class SystemBEntryAdmin(admin.ModelAdmin):
    list_display = ["entry_id", "record_ref_raw", "record_ref_normalized", "value", "has_issues"]
    list_filter = ["location__org"]
    search_fields = ["entry_id", "record_ref_raw"]

    @admin.display(boolean=True)
    def has_issues(self, obj):
        return bool(obj.import_issues)