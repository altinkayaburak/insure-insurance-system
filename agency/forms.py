from django import forms
from .models import AgencyPasswords,Agency

class AgencyPasswordForm(forms.ModelForm):
    class Meta:
        model = AgencyPasswords
        fields = ['username', 'password', 'partaj_code', 'web_username', 'web_password', 'cookie']


class AgencyLogoForm(forms.ModelForm):
    class Meta:
        model = Agency
        fields = ['logo']
