from django import forms
from django.utils import timezone

from .models import VisitorRecord


class VisitorRecordForm(forms.ModelForm):
    class Meta:
        model = VisitorRecord
        fields = ["visit_time", "gate", "visitor_count", "ticket_type", "weather"]
        widgets = {
            "visit_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "weather": forms.TextInput(attrs={"placeholder": "如：晴、多云、小雨"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["visit_time"].input_formats = ["%Y-%m-%dT%H:%M"]
        if not self.initial.get("visit_time") and not self.instance.pk:
            self.initial["visit_time"] = timezone.localtime().strftime("%Y-%m-%dT%H:%M")

        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field-control")
