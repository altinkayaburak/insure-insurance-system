from .models import Key, Parameter, KeyParameters, InsuranceCompany, ServiceConfiguration
from django import forms



class KeyForm(forms.ModelForm):
    class Meta:
        model = Key
        fields = ['KeyName', 'Description', 'InputType', 'MinLength', 'MaxLength', 'RegexPattern', 'IsActive']


class ParameterForm(forms.ModelForm):
    class Meta:
        model = Parameter
        fields = ['ParameterName', 'DefaultValue', 'IsActive']

class KeyParametersForm(forms.ModelForm):
    class Meta:
        model = KeyParameters
        fields = ['KeyID', 'ParameterID']

class InsuranceCompanyForm(forms.ModelForm):
    class Meta:
        model = InsuranceCompany
        fields = ['name', 'company_code', 'is_active']

class ServiceConfigurationForm(forms.ModelForm):
    class Meta:
        model = ServiceConfiguration
        fields = ['insurance_company', 'service_name', 'url', 'soap_action', 'soap_template']
        widgets = {
            'soap_template': forms.Textarea(attrs={'rows': 6, 'style': 'font-family: monospace;'})
        }